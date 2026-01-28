import shlex
from collections.abc import Generator
from pathlib import Path
from typing import Final

import ocp_resources.network_config_openshift_io as openshift_nc
import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.config_map import ConfigMap
from ocp_resources.namespace import Namespace
from ocp_resources.network_attachment_definition import OVNOverlayNetworkAttachmentDefinition
from ocp_resources.node import Node

from libs.net import netattachdef as libnad
from libs.net.traffic_generator import PodTcpClient as TcpClient
from libs.net.traffic_generator import TcpServer
from libs.net.udn import UDN_BINDING_DEFAULT_PLUGIN_NAME, create_udn_namespace
from libs.net.vmspec import IP_ADDRESS, lookup_iface_status, lookup_primary_network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs import nodenetworkconfigurationpolicy as libnncp
from tests.network.libs.bgp import (
    EXTERNAL_FRR_POD_LABEL,
    POD_SECONDARY_IFACE_NAME,
    ExternalFrrPodInfo,
    create_cudn_route_advertisements,
    create_frr_configuration,
    deploy_external_frr_pod,
    enable_route_advertisements_in_cluster,
    generate_frr_conf,
    wait_for_bgp_connection_established,
)
from tests.network.libs.ip import random_ipv4_address
from tests.network.libs.label_selector import LabelSelector
from tests.network.libs.vm_factory import udn_vm
from utilities.infra import get_node_selector_dict

APP_CUDN_LABEL: Final[dict] = {"app": "cudn"}
BGP_DATA_PATH: Final[Path] = Path(__file__).resolve().parent / "data" / "frr-config"
CUDN_BGP_LABEL: Final[dict] = {"cudn-bgp": "blue"}
CUDN_SUBNET_IPV4: Final[str] = "192.168.10.0/24"
EXTERNAL_PROVIDER_SUBNET_IPV4: Final[str] = f"{random_ipv4_address(net_seed=1, host_address=0)}/24"
EXTERNAL_PROVIDER_IP_V4: Final[str] = f"{random_ipv4_address(net_seed=1, host_address=150)}/24"
IPERF3_SERVER_PORT: Final[int] = 2354
LOCALNET_NETWORK_NAME: Final[str] = "localnet-network-bgp"


@pytest.fixture(scope="module")
def nncp_localnet_node1(
    nmstate_dependent_placeholder,
    admin_client: DynamicClient,
    worker_node1: Node,
) -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    desired_state = libnncp.DesiredState(
        ovn=libnncp.OVN([
            libnncp.BridgeMappings(
                localnet=LOCALNET_NETWORK_NAME,
                bridge=libnncp.DEFAULT_OVN_EXTERNAL_BRIDGE,
                state=libnncp.BridgeMappings.State.PRESENT.value,
            )
        ])
    )
    with libnncp.NodeNetworkConfigurationPolicy(
        client=admin_client,
        name="localnet-nncp-bgp",
        desired_state=desired_state,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp


@pytest.fixture(scope="module")
def nad_localnet(
    admin_client: DynamicClient,
    nncp_localnet_node1: libnncp.NodeNetworkConfigurationPolicy,
    cnv_tests_utilities_namespace: Namespace,
):
    with OVNOverlayNetworkAttachmentDefinition(
        client=admin_client,
        name="localnet-nad-bgp",
        namespace=cnv_tests_utilities_namespace.name,
        topology="localnet",
        network_name=LOCALNET_NETWORK_NAME,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def frr_configmap(
    workers: list[Node],
    cnv_tests_utilities_namespace: Namespace,
    admin_client: DynamicClient,
    nncp_localnet_node1: libnncp.NodeNetworkConfigurationPolicy,
) -> Generator[ConfigMap]:
    node_name_with_nncp = nncp_localnet_node1.node_selector["kubernetes.io/hostname"]
    frr_conf = generate_frr_conf(
        external_subnet_ipv4=EXTERNAL_PROVIDER_SUBNET_IPV4,
        nodes_ipv4_list=[worker.internal_ip for worker in workers if worker.name != node_name_with_nncp],
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
def cudn_layer2(
    admin_client: DynamicClient,
    namespace_cudn: Namespace,
) -> Generator[libcudn.ClusterUserDefinedNetwork]:
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
        client=admin_client,
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
def frr_configuration_created(admin_client: DynamicClient, frr_external_pod: ExternalFrrPodInfo) -> Generator[None]:
    with create_frr_configuration(
        name="frr-configuration-bgp",
        frr_pod_ipv4=frr_external_pod.ipv4,
        external_subnet_ipv4=EXTERNAL_PROVIDER_SUBNET_IPV4,
        client=admin_client,
    ):
        yield


@pytest.fixture(scope="module")
def frr_external_pod(
    nad_localnet: libnad.NetworkAttachmentDefinition,
    worker_node1: Node,
    frr_configmap: ConfigMap,
    cnv_tests_utilities_namespace: Namespace,
    admin_client: DynamicClient,
) -> Generator[ExternalFrrPodInfo]:
    with deploy_external_frr_pod(
        namespace_name=cnv_tests_utilities_namespace.name,
        node_name=worker_node1.name,
        nad_name=nad_localnet.name,
        frr_configmap_name=frr_configmap.name,
        client=admin_client,
    ) as pod_info:
        # Assign a secondary IP on the secondary interface to emulate the external provider subnet
        pod_info.pod.execute(
            command=shlex.split(f"ip addr add {EXTERNAL_PROVIDER_IP_V4} dev {POD_SECONDARY_IFACE_NAME}"),
            container="frr",
        )
        yield pod_info


@pytest.fixture(scope="module")
def bgp_setup_ready(
    frr_external_pod: ExternalFrrPodInfo,
    cudn_route_advertisements: None,
    frr_configuration_created: None,
    workers: list[Node],
) -> None:
    node_names = [worker.name for worker in workers if worker.name != frr_external_pod.pod.instance.spec.nodeName]
    wait_for_bgp_connection_established(node_names=node_names)


@pytest.fixture(scope="module")
def vm_cudn(
    namespace_cudn: Namespace,
    cudn_layer2: libcudn.ClusterUserDefinedNetwork,
    admin_client: DynamicClient,
    frr_external_pod: ExternalFrrPodInfo,
) -> Generator[BaseVirtualMachine]:
    with udn_vm(
        namespace_name=namespace_cudn.name,
        name="vm-cudn-bgp",
        client=admin_client,
        binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
        template_labels=EXTERNAL_FRR_POD_LABEL,
        anti_affinity_namespaces=[frr_external_pod.pod.namespace],
    ) as vm:
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
    frr_external_pod: ExternalFrrPodInfo, vm_cudn: BaseVirtualMachine, tcp_server_cudn_vm: TcpServer
) -> Generator[TcpClient]:
    with TcpClient(
        pod=frr_external_pod.pod,
        server_ip=lookup_iface_status(vm=vm_cudn, iface_name=lookup_primary_network(vm=vm_cudn).name)[IP_ADDRESS],
        server_port=IPERF3_SERVER_PORT,
        bind_interface=EXTERNAL_PROVIDER_IP_V4.split("/")[0],
    ) as client:
        yield client
