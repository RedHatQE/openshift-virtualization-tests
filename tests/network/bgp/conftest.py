from collections.abc import Generator
from pathlib import Path
from typing import Final

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.config_map import ConfigMap
from ocp_resources.namespace import Namespace
from ocp_resources.network_config_openshift_io import Network
from ocp_resources.node import Node
from ocp_resources.pod import Pod

from libs.net import netattachdef as libnad
from libs.net.bgp import (
    create_cudn_route_advertisements,
    create_frr_configuration,
    deploy_external_frr_pod,
    enable_ra_in_cluster_network_resource,
    generate_frr_conf,
)
from tests.network.constants import UDN_NS_LABEL
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs import nodenetworkconfigurationpolicy as libnncp
from tests.network.libs.label_selector import LabelSelector
from utilities.infra import create_ns, get_node_selector_dict

APP_CUDN_LABEL: Final[dict] = {"app": "cudn"}
BGP_DATA_PATH: Final[Path] = Path(__file__).resolve().parent / "data" / "frr-config"
CLUSTER_TLV2_GW_IPV4 = "10.46.248.1"
CLUSTER_TLV2_SUBNET_IPV4 = "10.46.248.0/21"
CUDN_BGP_LABEL: Final[dict] = {"cudn-bgp": "blue"}
CUDN_SUBNET_IPV4: Final[str] = "192.168.10.0/24"
EXTERNAL_FRR_STATIC_IPV4 = "10.46.248.177"  # Reserved IP for the external FRR pod
EXTERNAL_SUBNET_IPV4: Final[str] = "172.100.0.0/16"
VLAN_TAG: Final[int] = 153


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
            rangeStart=EXTERNAL_FRR_STATIC_IPV4,
            rangeEnd=EXTERNAL_FRR_STATIC_IPV4,
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
        frr_config_file_path.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def cluster_network_resource_ra_enabled(network_operator: Network, admin_client) -> Generator[None]:
    """Enables Route Advertisement in the Network Cluster Resource."""
    with enable_ra_in_cluster_network_resource(network_resource=network_operator, client=admin_client):
        yield


@pytest.fixture(scope="module")
def namespace_cudn(admin_client: DynamicClient) -> Generator[Namespace]:
    yield from create_ns(
        name="test-cudn-bgp-ns",
        labels={**UDN_NS_LABEL, **CUDN_BGP_LABEL},
        admin_client=admin_client,
    )


@pytest.fixture(scope="module")
def cudn_layer2(namespace_cudn: Namespace, admin_client: DynamicClient) -> Generator[libcudn.ClusterUserDefinedNetwork]:
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
        client=admin_client,
    ) as cudn:
        cudn.wait_for_status_success()
        yield cudn


@pytest.fixture(scope="module")
def cudn_route_advertisements(
    cudn_layer2: libcudn.ClusterUserDefinedNetwork,
    cluster_network_resource_ra_enabled: None,
    admin_client: DynamicClient,
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
        node_name=worker_node1.name,
        nad_name=macvlan_nad.name,
        frr_configmap_name=frr_configmap.name,
        default_route=CLUSTER_TLV2_GW_IPV4,
        client=admin_client,
    ) as pod:
        yield pod
