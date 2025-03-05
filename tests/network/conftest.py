# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import logging

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.namespace import Namespace
from ocp_resources.network_config_openshift_io import Network
from ocp_resources.pod import Pod
from pytest_testconfig import config as py_config

from tests.network.constants import BRCNV
from tests.network.utils import get_vlan_index_number, vm_for_brcnv_tests
from utilities.constants import (
    CLUSTER,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    IPV4_STR,
    IPV6_STR,
    ISTIO_SYSTEM_DEFAULT_NS,
    OVS_BRIDGE,
    VIRT_HANDLER,
)
from utilities.infra import ExecCommandOnPod, exit_pytest_execution, get_deployment_by_name, get_node_selector_dict
from utilities.network import get_cluster_cni_type, ip_version_data_from_matrix, network_nad

LOGGER = logging.getLogger(__name__)


def get_index_number():
    num = 1
    while True:
        yield num
        num += 1


@pytest.fixture(scope="session")
def index_number():
    return get_index_number()


@pytest.fixture(scope="session")
def virt_handler_pod(admin_client):
    for pod in Pod.get(
        dyn_client=admin_client,
        label_selector=f"{Pod.ApiGroup.KUBEVIRT_IO}={VIRT_HANDLER}",
    ):
        return pod

    raise ResourceNotFoundError(f"No {VIRT_HANDLER} Pod found.")


@pytest.fixture(scope="session")
def dual_stack_cluster(ipv4_supported_cluster, ipv6_supported_cluster):
    return ipv4_supported_cluster and ipv6_supported_cluster


@pytest.fixture()
def fail_if_not_ipv4_supported_cluster_from_mtx(
    request,
    ipv4_supported_cluster,
):
    if ip_version_data_from_matrix(request=request) == IPV4_STR and not ipv4_supported_cluster:
        pytest.fail(reason="IPv4 is not supported in this cluster")


@pytest.fixture()
def fail_if_not_ipv6_supported_cluster_from_mtx(
    request,
    ipv6_supported_cluster,
):
    if ip_version_data_from_matrix(request=request) == IPV6_STR and not ipv6_supported_cluster:
        pytest.fail(reason="IPv6 is not supported in this cluster")


@pytest.fixture()
def worker_node1_pod_executor(workers_utility_pods, worker_node1):
    return ExecCommandOnPod(utility_pods=workers_utility_pods, node=worker_node1)


@pytest.fixture(scope="module")
def dual_stack_network_data(ipv6_supported_cluster):
    if ipv6_supported_cluster:
        return {
            "ethernets": {
                "eth0": {
                    "dhcp4": True,
                    "addresses": ["fd10:0:2::2/120"],
                    "gateway6": "fd10:0:2::1",
                },
            },
        }


@pytest.fixture(scope="session")
def istio_system_namespace(admin_client):
    return Namespace(name=ISTIO_SYSTEM_DEFAULT_NS, client=admin_client).exists


@pytest.fixture(scope="module")
def sriov_workers_node1(sriov_workers):
    """
    Get first worker nodes with SR-IOV capabilities
    """
    return sriov_workers[0]


@pytest.fixture(scope="class")
def sriov_workers_node2(sriov_workers):
    """
    Get second worker nodes with SR-IOV capabilities
    """
    return sriov_workers[1]


@pytest.fixture(scope="session")
def vlans_list():
    vlans = py_config["vlans"]
    if not isinstance(vlans, list):
        vlans = vlans.split(",")
    return [int(_id) for _id in vlans]


@pytest.fixture(scope="module")
def vlan_index_number(vlans_list):
    return get_vlan_index_number(vlans_list=vlans_list)


@pytest.fixture(scope="module")
def brcnv_ovs_nad_vlan_1(
    hyperconverged_ovs_annotations_enabled_scope_session,
    namespace,
    vlan_index_number,
):
    vlan_tag = next(vlan_index_number)
    with network_nad(
        namespace=namespace,
        nad_type=OVS_BRIDGE,
        nad_name=f"{BRCNV}-{vlan_tag}",
        interface_name=BRCNV,
        vlan=vlan_tag,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def brcnv_vma_with_vlan_1(
    unprivileged_client,
    namespace,
    worker_node1,
    brcnv_ovs_nad_vlan_1,
):
    yield from vm_for_brcnv_tests(
        vm_name="vma",
        namespace=namespace,
        unprivileged_client=unprivileged_client,
        nads=[brcnv_ovs_nad_vlan_1],
        address_suffix=1,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    )


@pytest.fixture(scope="session")
def cluster_network_mtu():
    network_resource = Network(name=CLUSTER)
    if not network_resource.exists:
        raise ResourceNotFoundError(f"{CLUSTER} Network resource not found.")

    return network_resource.instance.status.clusterNetworkMTU


@pytest.fixture(scope="session")
def network_overhead(ovn_kubernetes_cluster):
    # The cluster network overlay overhead that should be subtracted from the cluster MTU, based on
    # https://docs.openshift.com/container-platform/4.12/networking/changing-cluster-network-mtu.html#mtu-value-selection_changing-cluster-network-mtu
    return 100 if ovn_kubernetes_cluster else 50


@pytest.fixture(scope="session")
def cluster_hardware_mtu(network_overhead, cluster_network_mtu):
    # cluster_network_mtu contains the pod network MTU. We should add to it the network overlay to get the hardware MTU.
    return cluster_network_mtu + network_overhead


@pytest.fixture(scope="module")
def cnao_deployment(hco_namespace):
    return get_deployment_by_name(
        namespace_name=hco_namespace.name,
        deployment_name=CLUSTER_NETWORK_ADDONS_OPERATOR,
    )


@pytest.fixture(scope="session")
def ovn_kubernetes_cluster(admin_client):
    return get_cluster_cni_type(admin_client=admin_client) == "OVNKubernetes"


@pytest.fixture(scope="session", autouse=True)
def network_sanity(hosts_common_available_ports, junitxml_plugin):
    """
    Perform verification that the cluster is a multi-nic one otherwise exit run
    """
    # set a non-zero return code to indicate failure of network sanity
    network_sanity_failure_return_code = 91
    LOGGER.info("Verify cluster running network tests is a multi-nic one")
    if len(hosts_common_available_ports) <= 1:
        exit_pytest_execution(
            filename="network_cluster_sanity_failure.txt",
            return_code=network_sanity_failure_return_code,
            message=f"Cluster is not a multinic cluster, with {hosts_common_available_ports} common available ports",
            junitxml_property=junitxml_plugin,
        )
    LOGGER.info(f"Validated network lane is running against a multinic-cluster: {hosts_common_available_ports}")
