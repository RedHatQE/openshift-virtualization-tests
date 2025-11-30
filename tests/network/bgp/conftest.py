import os
import shlex
from collections.abc import Generator
from pathlib import Path
from typing import Final

import ocp_resources.network_config_openshift_io as openshift_nc
import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.config_map import ConfigMap
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node
from ocp_resources.pod import Pod

from libs.net import netattachdef as libnad
from libs.net.traffic_generator import PodTcpClient as TcpClient
from libs.net.traffic_generator import TcpServer
from libs.net.udn import create_udn_namespace
from libs.net.vmspec import IP_ADDRESS, lookup_iface_status, lookup_primary_network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs import nodenetworkconfigurationpolicy as libnncp
from tests.network.libs.bgp import (
    POD_SECONDARY_IFACE_NAME,
    create_cudn_route_advertisements,
    create_frr_configuration,
    deploy_external_frr_pod,
    enable_route_advertisements_in_cluster,
    generate_frr_conf,
    wait_for_bgp_connection_established,
)
from tests.network.libs.ip import random_ipv4_address
from tests.network.libs.label_selector import LabelSelector
from tests.network.libs.nodenetworkstate import DEFAULT_ROUTE_V4, lookup_br_ex_gateway_v4
from tests.network.libs.vm_factory import udn_vm
from utilities.infra import get_node_selector_dict

APP_CUDN_LABEL: Final[dict] = {"app": "cudn"}
BGP_DATA_PATH: Final[Path] = Path(__file__).resolve().parent / "data" / "frr-config"
CUDN_BGP_LABEL: Final[dict] = {"cudn-bgp": "blue"}
CUDN_SUBNET_IPV4: Final[str] = "192.168.10.0/24"
EXTERNAL_PROVIDER_SUBNET_IPV4: Final[str] = f"{random_ipv4_address(net_seed=1, host_address=0)}/24"
EXTERNAL_PROVIDER_IP_V4: Final[str] = f"{random_ipv4_address(net_seed=1, host_address=150)}/24"
IPERF3_SERVER_PORT: Final[int] = 2354


@pytest.fixture(scope="session")
def vlan_nncp(
    admin_client: DynamicClient,
    vlan_base_iface: str,
    worker_node1: Node,
) -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    with libnncp.NodeNetworkConfigurationPolicy(
        client=admin_client,
        name="test-vlan-nncp",
        desired_state=libnncp.DesiredState(
            interfaces=[
                libnncp.Interface(
                    name=f"{vlan_base_iface}.{os.environ['PRIMARY_NODE_NETWORK_VLAN_TAG']}",
                    state=libnncp.NodeNetworkConfigurationPolicy.Interface.State.UP,
                    type="vlan",
                    vlan=libnncp.Vlan(id=int(os.environ["PRIMARY_NODE_NETWORK_VLAN_TAG"]), base_iface=vlan_base_iface),
                )
            ]
        ),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp


@pytest.fixture(scope="session")
def br_ex_gateway_v4(worker_node1: Node, admin_client: DynamicClient) -> str:
    return lookup_br_ex_gateway_v4(node_name=worker_node1.name, client=admin_client)


@pytest.fixture(scope="session")
def macvlan_nad(
    vlan_nncp: libnncp.NodeNetworkConfigurationPolicy,
    cnv_tests_utilities_namespace: Namespace,
    br_ex_gateway_v4: str,
    admin_client: DynamicClient,
) -> Generator[libnad.NetworkAttachmentDefinition]:
    macvlan_config = libnad.CNIPluginMacvlanConfig(
        master=vlan_nncp.instance.spec.desiredState.interfaces[0].name,
        ipam=libnad.IpamStatic(
            addresses=[
                libnad.IpamStatic.Address(address=os.environ["EXTERNAL_FRR_STATIC_IPV4"], gateway=br_ex_gateway_v4)
            ],
            routes=[libnad.IpamRoute(dst=DEFAULT_ROUTE_V4.dst, gw=br_ex_gateway_v4)],
        ),
    )

    with libnad.NetworkAttachmentDefinition(
        name="macvlan-nad-bgp",
        namespace=cnv_tests_utilities_namespace.name,
        config=libnad.NetConfig(name="macvlan-nad-bgp", plugins=[macvlan_config]),
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def frr_configmap(
    workers: list[Node], cnv_tests_utilities_namespace: Namespace, admin_client: DynamicClient
) -> Generator[ConfigMap]:
    frr_conf = generate_frr_conf(
        external_subnet_ipv4=EXTERNAL_PROVIDER_SUBNET_IPV4,
        nodes_ipv4_list=[worker.internal_ip for worker in workers],
    )

    with ConfigMap(
        name="frr-config",
        namespace=cnv_tests_utilities_namespace.name,
        data={
            "daemons": (BGP_DATA_PATH / "daemons").read_text(),
            "frr.conf": frr_conf,
        },
        client=admin_client,
    ) as cm:
        yield cm


@pytest.fixture(scope="module")
def cluster_network_resource_ra_enabled(
    network_operator: openshift_nc.Network,
    admin_client: DynamicClient,
) -> Generator[None]:
    with enable_route_advertisements_in_cluster(network_resource=network_operator, client=admin_client):
        yield


@pytest.fixture(scope="module")
def namespace_cudn(admin_client: DynamicClient) -> Generator[Namespace]:
    yield from create_udn_namespace(name="test-cudn-bgp-ns", client=admin_client, labels={**CUDN_BGP_LABEL})


@pytest.fixture(scope="module")
def cudn_layer2(namespace_cudn: Namespace) -> Generator[libcudn.ClusterUserDefinedNetwork]:
    with libcudn.ClusterUserDefinedNetwork(
        name="l2-network-cudn",
        namespace_selector=LabelSelector(matchLabels=CUDN_BGP_LABEL),
        network=libcudn.Network(
            topology=libcudn.Network.Topology.LAYER2.value,
            layer2=libcudn.Layer2(
                role=libcudn.Layer2.Role.PRIMARY.value,
                ipam=libcudn.Ipam(mode=libcudn.Ipam.Mode.ENABLED.value, lifecycle="Persistent"),
                subnets=[CUDN_SUBNET_IPV4],
            ),
        ),
        label=APP_CUDN_LABEL,
    ) as cudn:
        cudn.wait_for_status_success()
        yield cudn


@pytest.fixture(scope="module")
def cudn_route_advertisements(
    cudn_layer2: libcudn.ClusterUserDefinedNetwork,
    cluster_network_resource_ra_enabled: None,
    admin_client: DynamicClient,
) -> Generator[None]:
    with create_cudn_route_advertisements(
        name="cudn-route-advertisement", match_labels=APP_CUDN_LABEL, client=admin_client
    ):
        yield


@pytest.fixture(scope="module")
def frr_configuration_created(admin_client: DynamicClient) -> Generator[None]:
    with create_frr_configuration(
        name="frr-configuration-bgp",
        frr_pod_ipv4=os.environ["EXTERNAL_FRR_STATIC_IPV4"].split("/")[0],
        external_subnet_ipv4=EXTERNAL_PROVIDER_SUBNET_IPV4,
        client=admin_client,
    ):
        yield


@pytest.fixture(scope="module")
def frr_external_pod(
    macvlan_nad: libnad.NetworkAttachmentDefinition,
    worker_node1: Node,
    frr_configmap: ConfigMap,
    cnv_tests_utilities_namespace: Namespace,
    br_ex_gateway_v4: str,
    admin_client: DynamicClient,
) -> Generator[Pod]:
    with deploy_external_frr_pod(
        namespace_name=cnv_tests_utilities_namespace.name,
        node_name=worker_node1.name,
        nad_name=macvlan_nad.name,
        frr_configmap_name=frr_configmap.name,
        default_route=br_ex_gateway_v4,
        client=admin_client,
    ) as pod:
        # Assign a secondary IP on the secondary interface to emulate the external provider subnet
        pod.execute(
            command=shlex.split(f"ip addr add {EXTERNAL_PROVIDER_IP_V4} dev {POD_SECONDARY_IFACE_NAME}"),
            container="frr",
        )
        yield pod


@pytest.fixture(scope="module")
def bgp_setup_ready(
    frr_external_pod: Pod,
    cudn_route_advertisements: None,
    frr_configuration_created: None,
    workers: list[Node],
) -> None:
    node_names = [worker.name for worker in workers]
    wait_for_bgp_connection_established(node_names=node_names)


@pytest.fixture(scope="module")
def vm_cudn(
    namespace_cudn: Namespace,
    cudn_layer2: libcudn.ClusterUserDefinedNetwork,
    admin_client: DynamicClient,
) -> Generator[BaseVirtualMachine]:
    with udn_vm(namespace_name=namespace_cudn.name, name="vm-cudn-bgp", client=admin_client) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="module")
def tcp_server_cudn_vm(vm_cudn: BaseVirtualMachine) -> Generator[TcpServer]:
    with TcpServer(vm=vm_cudn, port=IPERF3_SERVER_PORT) as server:
        if not server.is_running():
            raise ProcessLookupError("Iperf3 server process is not running in the VM")
        yield server


@pytest.fixture(scope="module")
def tcp_client_external_network(
    frr_external_pod: Pod, vm_cudn: BaseVirtualMachine, tcp_server_cudn_vm: TcpServer
) -> Generator[TcpClient]:
    with TcpClient(
        pod=frr_external_pod,
        server_ip=lookup_iface_status(vm=vm_cudn, iface_name=lookup_primary_network(vm=vm_cudn).name)[IP_ADDRESS],
        server_port=IPERF3_SERVER_PORT,
        bind_interface=EXTERNAL_PROVIDER_IP_V4.split("/")[0],
    ) as client:
        yield client
