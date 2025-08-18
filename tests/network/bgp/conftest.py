import os
from collections.abc import Generator
from pathlib import Path
from typing import Final

import pytest
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
from libs.net.node_network import DEFAULT_ROUTE_DEST_V4, BrExNetworkInfo, lookup_br_ex_network_info
from libs.net.udn import create_udn_namespace
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs import nodenetworkconfigurationpolicy as libnncp
from tests.network.libs.label_selector import LabelSelector
from utilities.infra import cache_admin_client, get_node_selector_dict

APP_CUDN_LABEL: Final[dict] = {"app": "cudn"}
BGP_DATA_PATH: Final[Path] = Path(__file__).resolve().parent / "data" / "frr-config"
CUDN_BGP_LABEL: Final[dict] = {"cudn-bgp": "blue"}
CUDN_SUBNET_IPV4: Final[str] = "192.168.10.0/24"
EXTERNAL_SUBNET_IPV4: Final[str] = "172.100.0.0/16"


@pytest.fixture(scope="module")
def vlan_nncp(vlan_base_iface: str, worker_node1: Node) -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    """Creates a NodeNetworkConfigurationPolicy with a VLAN interface on the specified cluster's node."""
    with libnncp.NodeNetworkConfigurationPolicy(
        name="test-vlan-nncp",
        desired_state=libnncp.DesiredState(
            interfaces=[
                libnncp.Interface(
                    name=f"{vlan_base_iface}.{os.environ['VLAN_TAG']}",
                    state=libnncp.NodeNetworkConfigurationPolicy.Interface.State.UP,
                    type="vlan",
                    vlan=libnncp.Vlan(id=int(os.environ["VLAN_TAG"]), base_iface=vlan_base_iface),
                )
            ]
        ),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp


@pytest.fixture(scope="session")
def br_ex_network_info(worker_node1: Node) -> BrExNetworkInfo:
    """Retrieves cluster node network information."""
    return lookup_br_ex_network_info(node_name=worker_node1.name)


@pytest.fixture(scope="module")
def macvlan_nad(
    vlan_nncp: libnncp.NodeNetworkConfigurationPolicy,
    cnv_tests_utilities_namespace: Namespace,
    br_ex_network_info: BrExNetworkInfo,
) -> Generator[libnad.NetworkAttachmentDefinition]:
    macvlan_config = libnad.CNIPluginMacvlanConfig(
        master=vlan_nncp.instance.spec.desiredState.interfaces[0].name,
        ipam=libnad.Ipam(
            type="host-local",
            subnet=br_ex_network_info.cidr_v4,
            rangeStart=os.environ["EXTERNAL_FRR_STATIC_IPV4"],
            rangeEnd=os.environ["EXTERNAL_FRR_STATIC_IPV4"],
            gateway=br_ex_network_info.gateway_v4,
            routes=[libnad.IpamRoute(dst=DEFAULT_ROUTE_DEST_V4, gw=br_ex_network_info.gateway_v4)],
        ),
    )

    with libnad.NetworkAttachmentDefinition(
        name="macvlan-nad-bgp",
        namespace=cnv_tests_utilities_namespace.name,
        config=libnad.NetConfig(name="macvlan-nad-bgp", plugins=[macvlan_config]),
        client=cache_admin_client(),
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def frr_configmap(workers: list[Node], cnv_tests_utilities_namespace: Namespace) -> Generator[ConfigMap]:
    """Generates a ConfigMap containing the config files for the external FRR."""
    frr_config_file_path = BGP_DATA_PATH / "frr.conf"
    generate_frr_conf(
        output_file=frr_config_file_path,
        external_subnet_ipv4=EXTERNAL_SUBNET_IPV4,
        nodes_ipv4_list=[worker.internal_ip for worker in workers],
    )

    with ConfigMap(
        name="frr-config",
        namespace=cnv_tests_utilities_namespace.name,
        data={
            "daemons": (BGP_DATA_PATH / "daemons").read_text(),
            "frr.conf": frr_config_file_path.read_text(),
        },
        client=cache_admin_client(),
    ) as cm:
        yield cm
        frr_config_file_path.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def cluster_network_resource_ra_enabled(network_operator: Network) -> Generator[None]:
    """Enables Route Advertisement in the Network Cluster Resource."""
    with enable_ra_in_cluster_network_resource(network_resource=network_operator):
        yield


@pytest.fixture(scope="module")
def namespace_cudn() -> Generator[Namespace]:
    yield from create_udn_namespace(name="test-cudn-bgp-ns", labels={**CUDN_BGP_LABEL})


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
) -> Generator[None]:
    """Creates a Route Advertisement for the CUDN."""
    with create_cudn_route_advertisements(name="cudn-route-advertisement", match_labels=APP_CUDN_LABEL):
        yield


@pytest.fixture(scope="module")
def frr_configuration() -> Generator[None]:
    with create_frr_configuration(
        name="frr-configuration-bgp",
        frr_pod_ipv4=os.environ["EXTERNAL_FRR_STATIC_IPV4"],
        external_subnet_ipv4=EXTERNAL_SUBNET_IPV4,
    ):
        yield


@pytest.fixture(scope="module")
def frr_external_pod(
    macvlan_nad: libnad.NetworkAttachmentDefinition,
    worker_node1: Node,
    frr_configmap: ConfigMap,
    cnv_tests_utilities_namespace: Namespace,
    br_ex_network_info: BrExNetworkInfo,
) -> Generator[Pod]:
    """Deploys an external FRR pod with BGP configuration."""
    with deploy_external_frr_pod(
        namespace_name=cnv_tests_utilities_namespace.name,
        node_name=worker_node1.name,
        nad_name=macvlan_nad.name,
        frr_configmap_name=frr_configmap.name,
        default_route=br_ex_network_info.gateway_v4,
    ) as pod:
        yield pod
