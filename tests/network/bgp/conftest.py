from collections.abc import Generator
from pathlib import Path

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.config_map import ConfigMap
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node
from ocp_resources.pod import Pod

from libs.net import netattachdef as libnad
from libs.net.bgp import (
    create_cudn_route_advertisements,
    create_frr_configuration,
    deploy_external_frr_pod,
    enable_ra_in_network_operator,
    generate_frr_conf,
)
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs import nodenetworkconfigurationpolicy as libnncp
from tests.network.libs.cluster_user_defined_network import Network
from tests.network.libs.label_selector import LabelSelector
from utilities.infra import create_ns, get_node_selector_dict

APP_CUDN_LABEL = {"app": "cudn"}
BGP_DATA_PATH = Path(__file__).resolve().parent / "data" / "frr-config"
CLUSTER_TLV2_GW_IPV4 = "10.46.248.1"
CLUSTER_TLV2_SUBNET_IPV4 = "10.46.248.0/21"
CUDN_BGP_LABEL = {"cudn-bgp": "blue"}
CUDN_SUBNET_IPV4 = "192.168.10.0/24"
EXTERNAL_FRR_STATIC_IPV4 = "10.46.248.199"  # Reserved IP for the external FRR pod
EXTERNAL_SUBNET_IPV4 = "172.100.0.0/16"
VLAN_TAG = 153


@pytest.fixture(scope="module")
def vlan_nncp(
    vlan_base_iface: str, worker_node1: Node, admin_client: DynamicClient
) -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    """Creates a NodeNetworkConfigurationPolicy with a VLAN interface on the specified cluster's node."""
    with libnncp.NodeNetworkConfigurationPolicy(
        name="test-vlan-nncp",
        desired_state=libnncp.DesiredState(
            interfaces=[
                libnncp.Interface(
                    name=f"{vlan_base_iface}.{VLAN_TAG}",
                    state=libnncp.NodeNetworkConfigurationPolicy.Interface.State.UP,
                    type="vlan",
                    vlan=libnncp.Vlan(id=VLAN_TAG, base_iface=vlan_base_iface),
                )
            ]
        ),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        client=admin_client,
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp


@pytest.fixture(scope="module")
def macvlan_nad(
    vlan_nncp: libnncp.NodeNetworkConfigurationPolicy,
    cnv_tests_utilities_namespace: Namespace,
    admin_client: DynamicClient,
) -> Generator[libnad.NetworkAttachmentDefinition]:
    macvlan_config = libnad.CNIPluginMacvlanConfig(
        master=vlan_nncp.instance.spec.desiredState.interfaces[0].name,
        ipam=libnad.Ipam(
            type="host-local",
            subnet=CLUSTER_TLV2_SUBNET_IPV4,
            range_start=EXTERNAL_FRR_STATIC_IPV4,
            range_end=EXTERNAL_FRR_STATIC_IPV4,
            gateway=CLUSTER_TLV2_GW_IPV4,
            routes=[libnad.IpamRoute(dst="0.0.0.0/0", gw=CLUSTER_TLV2_GW_IPV4)],
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
    """Generates a ConfigMap containing the config files for the external FRR."""
    frr_config_file_path = BGP_DATA_PATH / "frr.conf"
    generate_frr_conf(
        output_file=frr_config_file_path,
        external_subnet_ipv4=EXTERNAL_SUBNET_IPV4,
        nodes_ipv4_list=[
            addr.address
            for worker in workers
            for addr in worker.instance.status.addresses
            if addr.type == "InternalIP" and "." in addr.address
        ],
    )

    with ConfigMap(
        name="frr-config",
        namespace=cnv_tests_utilities_namespace.name,
        data={
            "daemons": (BGP_DATA_PATH / "daemons").read_text(),
            "frr.conf": frr_config_file_path.read_text(),
        },
        client=admin_client,
    ) as cm:
        yield cm


@pytest.fixture(scope="module")
def network_operator_ra_enabled(network_operator: Network) -> Generator[None]:
    """Enables Route Advertisement in the Network Operator."""
    with enable_ra_in_network_operator(network_operator):
        yield


@pytest.fixture(scope="module")
def namespace_cudn(admin_client: DynamicClient) -> Generator[Namespace]:
    yield from create_ns(
        name="test-cudn-bgp-ns",
        labels={"k8s.ovn.org/primary-user-defined-network": "", **CUDN_BGP_LABEL},
        admin_client=admin_client,
    )


@pytest.fixture(scope="module")
def cudn_layer2(namespace_cudn: Namespace, admin_client: DynamicClient) -> Generator[libcudn.ClusterUserDefinedNetwork]:
    with libcudn.ClusterUserDefinedNetwork(
        name="l2-network-cudn",
        namespace_selector=LabelSelector(matchLabels=CUDN_BGP_LABEL),
        network=libcudn.Network(
            topology="Layer2",
            layer2=libcudn.Layer2(
                role="Primary",
                ipam=libcudn.Ipam(mode=libcudn.Ipam.Mode.ENABLED.value, lifecycle="Persistent"),
                subnets=[CUDN_SUBNET_IPV4],
            ),
        ),
        label=APP_CUDN_LABEL,
        client=admin_client,
    ) as cudn:
        cudn.wait_for_status_success()
        yield cudn


@pytest.fixture(scope="module")
def cudn_route_advertisements(
    cudn_layer2: libcudn.ClusterUserDefinedNetwork, network_operator_ra_enabled: None, admin_client: DynamicClient
) -> Generator[None]:
    """Creates a Route Advertisement for the CUDN."""
    with create_cudn_route_advertisements(
        name="cudn-route-advertisement", match_labels=APP_CUDN_LABEL, client=admin_client
    ):
        yield


@pytest.fixture(scope="module")
def frr_configuration(admin_client: DynamicClient) -> Generator[None]:
    with create_frr_configuration(
        name="frr-configuration-bgp",
        frr_pod_ipv4=EXTERNAL_FRR_STATIC_IPV4,
        external_subnet_ipv4=EXTERNAL_SUBNET_IPV4,
        client=admin_client,
    ):
        yield


@pytest.fixture(scope="module")
def frr_external_pod(
    macvlan_nad: libnad.NetworkAttachmentDefinition,
    worker_node1: Node,
    frr_configmap: ConfigMap,
    cnv_tests_utilities_namespace: Namespace,
    admin_client: DynamicClient,
) -> Generator[Pod]:
    """Deploys an external FRR pod with BGP configuration."""
    with deploy_external_frr_pod(
        namespace_name=cnv_tests_utilities_namespace.name,
        node_name=worker_node1.hostname,
        nad_name=macvlan_nad.name,
        frr_configmap_name=frr_configmap.name,
        default_route=CLUSTER_TLV2_GW_IPV4,
        client=admin_client,
    ) as pod:
        yield pod
