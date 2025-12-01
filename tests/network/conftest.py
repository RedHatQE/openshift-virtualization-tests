# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV network tests
"""

import logging
import os

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.namespace import Namespace
from ocp_resources.network_config_openshift_io import Network
from ocp_resources.performance_profile import PerformanceProfile
from ocp_resources.pod import Pod
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError

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
    NamespacesNames,
)
from utilities.infra import (
    ExecCommandOnPod,
    get_deployment_by_name,
    get_node_selector_dict,
    wait_for_pods_running,
)
from utilities.network import (
    get_cluster_cni_type,
    ip_version_data_from_matrix,
    network_nad,
)
from utilities.pytest_utils import exit_pytest_execution

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
def cluster_network_mtu(admin_client):
    network_resource = Network(name=CLUSTER, client=admin_client)
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


@pytest.fixture(scope="session")
def network_operator(admin_client):
    return Network(
        name=CLUSTER, api_group=Network.ApiGroup.OPERATOR_OPENSHIFT_IO, ensure_exists=True, client=admin_client
    )


@pytest.fixture(scope="session", autouse=True)
def network_sanity(
    admin_client,
    hosts_common_available_ports,
    junitxml_plugin,
    request,
    istio_system_namespace,
    cluster_network_mtu,
    network_overhead,
    sriov_workers,
    ipv4_supported_cluster,
    ipv6_supported_cluster,
    conformance_tests,
    nmstate_namespace,
):
    """
    Ensures the test cluster meets network requirements before executing tests.
    A failure in these checks results in pytest exiting with a predefined
    return code and a message recorded in JUnit XML.
    """
    failure_msgs = []
    collected_tests = request.session.items

    def _verify_multi_nic(_request):
        marker_args = _request.config.getoption("-m")
        # TODO: add multi_nic marker to tests that require multiple NICs
        if marker_args and "single_nic" in marker_args and "not single_nic" not in marker_args:
            LOGGER.info("Running only single-NIC network cases, no need to verify multi NIC support")
            return

        # TODO: network tests should be marked with multi_nic to allow explicit checks based on markers
        if conformance_tests:
            LOGGER.info(
                "Running conformance tests which run only single-nic tests, no need to verify multi NIC support"
            )
            return

        LOGGER.info("Verifying if the cluster has multiple NICs for network tests")
        if len(hosts_common_available_ports) <= 1:
            failure_msgs.append(
                f"Cluster lacks multiple NICs, only {hosts_common_available_ports} common available ports found"
            )
        else:
            LOGGER.info(f"Validated network lane is running against a multinic-cluster: {hosts_common_available_ports}")

    def _verify_dpdk():
        if any(test.get_closest_marker("dpdk") for test in collected_tests):
            LOGGER.info("Verifying if the cluster supports running DPDK tests...")
            dpdk_performance_profile_name = "dpdk"
            if not PerformanceProfile(name=dpdk_performance_profile_name, client=admin_client).exists:
                failure_msgs.append(
                    f"DPDK is not configured, the {PerformanceProfile.kind}/{dpdk_performance_profile_name} "
                    "does not exist"
                )
            else:
                LOGGER.info("Validated network lane is running against a DPDK-enabled cluster")

    def _verify_service_mesh():
        if any(test.get_closest_marker("service_mesh") for test in collected_tests):
            LOGGER.info("Verifying if the cluster supports running service-mesh tests...")
            if not istio_system_namespace:
                failure_msgs.append(
                    f"Service mesh operator is not installed, the '{ISTIO_SYSTEM_DEFAULT_NS}' namespace does not exist"
                )
            else:
                LOGGER.info(
                    "Validated service mesh operator is running against a valid cluster with "
                    f"'{ISTIO_SYSTEM_DEFAULT_NS}' namespace"
                )

    def _verify_jumbo_frame():
        if any(test.get_closest_marker("jumbo_frame") for test in collected_tests):
            LOGGER.info("Verifying if the cluster supports running jumbo frame tests...")
            minimum_required_mtu = 7950 - network_overhead
            if cluster_network_mtu < minimum_required_mtu:
                failure_msgs.append(
                    f"Cluster's network MTU is too small to support jumbo frame tests "
                    f"Current MTU: {cluster_network_mtu}, Minimum required MTU: {minimum_required_mtu}."
                )
            else:
                LOGGER.info(f"Cluster supports jumbo frame tests with an MTU of {cluster_network_mtu}")

    def _verify_sriov():
        if any(test.get_closest_marker("sriov") for test in collected_tests):
            LOGGER.info("Verifying if the cluster supports running SRIOV tests...")
            if not Namespace(name=py_config["sriov_namespace"], client=admin_client).exists:
                failure_msgs.append(
                    f"SRIOV operator is not installed, the '{py_config['sriov_namespace']}' namespace does not exist"
                )
            if len(sriov_workers) < 2:
                failure_msgs.append(
                    "SRIOV tests require at least 2 SRIOV-capable worker nodes, but fewer were detected"
                )
            else:
                LOGGER.info(
                    "Validated SRIOV operator is running against a valid cluster with "
                    f"'{py_config['sriov_namespace']}' namespace and "
                    f"has {len(sriov_workers)} SRIOV-capable worker nodes"
                )

    def _verify_ip_family(family, is_supported_in_cluster):
        if any(test.get_closest_marker(family) for test in collected_tests):
            LOGGER.info(f"Verifying if the cluster supports running {family} tests...")
            if not is_supported_in_cluster:
                failure_msgs.append(f"{family} is not supported in this cluster")
            else:
                LOGGER.info(f"Validated network lane is running against an {family} supported cluster")

    def _verify_bgp_env_vars():
        """Verify if the cluster supports running BGP tests.

        Requires the following environment variables to be set:
        PRIMARY_NODE_NETWORK_VLAN_TAG: expected VLAN number on the node br-ex interface.
        EXTERNAL_FRR_STATIC_IPV4: reserved IP in CIDR format for the external FRR pod inside
                                  PRIMARY_NODE_NETWORK_VLAN_TAG network.
        """
        if any(test.get_closest_marker("bgp") and not test.get_closest_marker("xfail") for test in collected_tests):
            LOGGER.info("Verifying if the cluster supports running BGP tests...")
            required_env_vars = [
                "PRIMARY_NODE_NETWORK_VLAN_TAG",
                "EXTERNAL_FRR_STATIC_IPV4",
            ]
            missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]

            if missing_env_vars:
                failure_msgs.append(f"BGP tests require the following environment variables: {missing_env_vars}")
                return

    def _verify_nmstate_running_pods(_admin_client, namespace):
        # TODO: Only test if nmstate is required by the test(s)
        if not namespace:
            failure_msgs.append(f"Knmstate namespace '{NamespacesNames.OPENSHIFT_NMSTATE}' does not exist.")
            return

        LOGGER.info("Verifying all pods in nmstate namespace are running")
        try:
            wait_for_pods_running(
                admin_client=_admin_client,
                namespace=namespace,
            )
        except TimeoutExpiredError:
            failure_msgs.append(f"Some pods are not running in nmstate namespace '{namespace.name}'")

    _verify_multi_nic(_request=request)
    _verify_dpdk()
    _verify_service_mesh()
    _verify_jumbo_frame()
    _verify_sriov()
    _verify_ip_family(family="ipv4", is_supported_in_cluster=ipv4_supported_cluster)
    _verify_ip_family(family="ipv6", is_supported_in_cluster=ipv6_supported_cluster)
    _verify_bgp_env_vars()
    _verify_nmstate_running_pods(_admin_client=admin_client, namespace=nmstate_namespace)

    if failure_msgs:
        err_msg = "\n".join(failure_msgs)
        LOGGER.error(f"Network cluster verification failed! Missing components:\n{err_msg}")
        exit_pytest_execution(
            message=err_msg,
            return_code=91,
            filename="network_cluster_sanity_failure.txt",
            junitxml_property=junitxml_plugin,
        )
