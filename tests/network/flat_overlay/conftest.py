import logging
import random

import pytest
from ocp_resources.multi_network_policy import MultiNetworkPolicy
from ocp_resources.resource import ResourceEditor

from tests.network.flat_overlay.constants import (
    CONNECTION_REQUESTS,
    HTTP_SUCCESS_RESPONSE_STR,
    LAYER2,
)
from tests.network.flat_overlay.utils import (
    NoAvailablePortError,
    create_flat_overlay_vm,
    create_ip_block,
    get_vm_connection_reply,
    get_vm_kubevirt_domain_label,
    is_port_number_available,
    start_nc_response_on_vm,
    wait_for_multi_network_policy_resources,
)
from tests.network.libs.ip import random_ipv4_address
from utilities.constants import FLAT_OVERLAY_STR
from utilities.infra import create_ns
from utilities.network import assert_ping_successful, get_vmi_ip_v4_by_name, network_nad
from utilities.virt import migrate_vm_and_verify

LOGGER = logging.getLogger(__name__)


FLAT_L2_STR = "flat-l2"
FLAT_L2_BASIC_NAD_NAME = f"{FLAT_L2_STR}-nad"
FLAT_L2_BASIC_NETWORK_NAME = f"{FLAT_L2_STR}-network"
VMA_VMB = "vma-vmb"
FLAT_OVERLAY_VMA_VMB_NAD_NAME = f"{FLAT_L2_BASIC_NAD_NAME}-{VMA_VMB}"
FLAT_OVERLAY_VMA_VMB_NETWORK_NAME = f"{FLAT_L2_BASIC_NETWORK_NAME}-{VMA_VMB}"
GENEVE_HEADER = 16
UDP_HEADER = 8
IPV4_HEADER = 20
ETHERNET_HEADER = 14
SPECIFIC_HOST_MASK = "32"


@pytest.fixture(scope="module")
def enable_multi_network_policy_usage(admin_client, network_operator):
    with ResourceEditor(patches={network_operator: {"spec": {"useMultiNetworkPolicy": True}}}):
        wait_for_multi_network_policy_resources(admin_client=admin_client, deploy_mnp_crd=True)
        yield
    wait_for_multi_network_policy_resources(admin_client=admin_client, deploy_mnp_crd=False)


@pytest.fixture(scope="module")
def flat_l2_port(
    workers_utility_pods,
    worker_node1,
):
    occupied_ports = []
    for index in range(1, 5):
        flat_l2_port = random.randint(
            49152,
            65535,  # Pick a random port number from the private range.
        )
        if is_port_number_available(
            workers_utility_pods=workers_utility_pods, worker_node1=worker_node1, port=flat_l2_port
        ):
            return flat_l2_port
        else:
            occupied_ports.append(flat_l2_port)
    raise NoAvailablePortError(
        f"No available port was found in the private port range. Ports checked:\n{occupied_ports}"
    )


@pytest.fixture(scope="module")
def flat_overlay_second_namespace(admin_client, unprivileged_client):
    yield from create_ns(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        name="test-flat-overlay-second-namespace",
    )


@pytest.fixture(scope="class")
def flat_overlay_vma_vmb_nad(namespace):
    with network_nad(
        nad_type=FLAT_OVERLAY_STR,
        network_name=FLAT_OVERLAY_VMA_VMB_NETWORK_NAME,
        nad_name=FLAT_OVERLAY_VMA_VMB_NAD_NAME,
        namespace=namespace,
        topology=LAYER2,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def flat_overlay_vmc_vmd_nad(namespace):
    nad_for_vms = "vmc-vmd"
    with network_nad(
        nad_type=FLAT_OVERLAY_STR,
        network_name=f"{FLAT_L2_BASIC_NETWORK_NAME}-{nad_for_vms}",
        nad_name=f"{FLAT_L2_BASIC_NAD_NAME}-{nad_for_vms}",
        namespace=namespace,
        topology=LAYER2,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def flat_overlay_vme_nad(flat_overlay_second_namespace):
    with network_nad(
        nad_type=FLAT_OVERLAY_STR,
        network_name=FLAT_OVERLAY_VMA_VMB_NETWORK_NAME,
        nad_name=FLAT_OVERLAY_VMA_VMB_NAD_NAME,
        namespace=flat_overlay_second_namespace,
        topology=LAYER2,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def flat_overlay_jumbo_frame_nad(namespace, cluster_hardware_mtu):
    with network_nad(
        nad_type=FLAT_OVERLAY_STR,
        network_name=f"{FLAT_L2_BASIC_NETWORK_NAME}-jumbo",
        nad_name=f"{FLAT_L2_BASIC_NAD_NAME}-jumbo",
        namespace=namespace,
        mtu=cluster_hardware_mtu,
        topology=LAYER2,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def vma_flat_overlay(
    unprivileged_client,
    worker_node1,
    index_number,
    flat_overlay_vma_vmb_nad,
):
    yield from create_flat_overlay_vm(
        vm_name=f"vma-{FLAT_L2_STR}",
        namespace_name=flat_overlay_vma_vmb_nad.namespace,
        nad_name=flat_overlay_vma_vmb_nad.name,
        unprivileged_client=unprivileged_client,
        host_ip_suffix=next(index_number),
        worker_node_hostname=worker_node1.hostname,
    )


@pytest.fixture(scope="class")
def vmb_flat_overlay(
    unprivileged_client,
    worker_node1,
    index_number,
    flat_overlay_vma_vmb_nad,
):
    yield from create_flat_overlay_vm(
        vm_name=f"vmb-{FLAT_L2_STR}",
        namespace_name=flat_overlay_vma_vmb_nad.namespace,
        nad_name=flat_overlay_vma_vmb_nad.name,
        unprivileged_client=unprivileged_client,
        host_ip_suffix=next(index_number),
        worker_node_hostname=worker_node1.hostname,
    )


@pytest.fixture(scope="class")
def vmc_flat_overlay(
    unprivileged_client,
    index_number,
    flat_overlay_vmc_vmd_nad,
):
    # This VM doesn't have a node selector since it will be migrated in a later step.
    yield from create_flat_overlay_vm(
        vm_name=f"vmc-{FLAT_L2_STR}",
        namespace_name=flat_overlay_vmc_vmd_nad.namespace,
        nad_name=flat_overlay_vmc_vmd_nad.name,
        unprivileged_client=unprivileged_client,
        host_ip_suffix=next(index_number),
    )


@pytest.fixture(scope="class")
def vmd_flat_overlay(
    unprivileged_client,
    worker_node1,
    index_number,
    flat_overlay_vmc_vmd_nad,
):
    yield from create_flat_overlay_vm(
        vm_name=f"vmd-{FLAT_L2_STR}",
        namespace_name=flat_overlay_vmc_vmd_nad.namespace,
        nad_name=flat_overlay_vmc_vmd_nad.name,
        unprivileged_client=unprivileged_client,
        host_ip_suffix=next(index_number),
        worker_node_hostname=worker_node1.hostname,
    )


@pytest.fixture(scope="class")
def vme_flat_overlay(
    unprivileged_client,
    worker_node3,
    index_number,
    flat_overlay_vme_nad,
):
    yield from create_flat_overlay_vm(
        vm_name=f"vme-{FLAT_L2_STR}",
        namespace_name=flat_overlay_vme_nad.namespace,
        nad_name=flat_overlay_vme_nad.name,
        unprivileged_client=unprivileged_client,
        host_ip_suffix=next(index_number),
        worker_node_hostname=worker_node3.hostname,
    )


@pytest.fixture(scope="class")
def vma_jumbo_flat_l2(
    unprivileged_client,
    worker_node1,
    index_number,
    flat_overlay_jumbo_frame_nad,
):
    yield from create_flat_overlay_vm(
        vm_name=f"vma-jumbo-{FLAT_L2_STR}",
        namespace_name=flat_overlay_jumbo_frame_nad.namespace,
        nad_name=flat_overlay_jumbo_frame_nad.name,
        unprivileged_client=unprivileged_client,
        host_ip_suffix=next(index_number),
        worker_node_hostname=worker_node1.hostname,
    )


@pytest.fixture(scope="class")
def vmb_jumbo_flat_l2(
    unprivileged_client,
    worker_node2,
    index_number,
    flat_overlay_jumbo_frame_nad,
):
    yield from create_flat_overlay_vm(
        vm_name=f"vmb-jumbo-{FLAT_L2_STR}",
        namespace_name=flat_overlay_jumbo_frame_nad.namespace,
        nad_name=flat_overlay_jumbo_frame_nad.name,
        unprivileged_client=unprivileged_client,
        host_ip_suffix=next(index_number),
        worker_node_hostname=worker_node2.hostname,
    )


@pytest.fixture(scope="module")
def flat_l2_jumbo_frame_packet_size(cluster_network_mtu):
    return cluster_network_mtu - GENEVE_HEADER - UDP_HEADER - IPV4_HEADER - ETHERNET_HEADER


@pytest.fixture(scope="class")
def vmc_flat_overlay_ip_address(vmc_flat_overlay, flat_overlay_vmc_vmd_nad):
    return get_vmi_ip_v4_by_name(vm=vmc_flat_overlay, name=flat_overlay_vmc_vmd_nad.name)


@pytest.fixture()
def ping_before_migration(vmd_flat_overlay, vmc_flat_overlay_ip_address):
    assert_ping_successful(
        src_vm=vmd_flat_overlay,
        dst_ip=vmc_flat_overlay_ip_address,
    )


@pytest.fixture()
def migrated_vmc_flat_overlay(vmc_flat_overlay):
    migrate_vm_and_verify(vm=vmc_flat_overlay, check_ssh_connectivity=True)


@pytest.fixture(scope="class")
def vmb_flat_overlay_ip_address(vmb_flat_overlay, flat_overlay_vma_vmb_nad):
    return get_vmi_ip_v4_by_name(vm=vmb_flat_overlay, name=flat_overlay_vma_vmb_nad.name)


@pytest.fixture(scope="class")
def vmd_flat_overlay_ip_address(vmd_flat_overlay, flat_overlay_vmc_vmd_nad):
    return get_vmi_ip_v4_by_name(vm=vmd_flat_overlay, name=flat_overlay_vmc_vmd_nad.name)


@pytest.fixture()
def vma_egress_multi_network_policy(
    admin_client,
    flat_overlay_vma_vmb_nad,
    vmb_flat_overlay_ip_address,
    vma_domain_label,
):
    with MultiNetworkPolicy(
        name="vma-egress-mnp",
        namespace=flat_overlay_vma_vmb_nad.namespace,
        network_name=flat_overlay_vma_vmb_nad.name,
        policy_types=["Egress"],
        egress=create_ip_block(
            ingress=False,
            ip_address=f"{vmb_flat_overlay_ip_address}/{SPECIFIC_HOST_MASK}",
        ),
        pod_selector={"matchLabels": vma_domain_label},
        client=admin_client,
    ) as mnp:
        yield mnp


@pytest.fixture()
def vmb_ingress_multi_network_policy(
    admin_client,
    flat_overlay_vma_vmb_nad,
    vmb_domain_label,
):
    with MultiNetworkPolicy(
        name="vmb-ingress-mnp",
        namespace=flat_overlay_vma_vmb_nad.namespace,
        pod_selector={"matchLabels": vmb_domain_label},
        network_name=flat_overlay_vma_vmb_nad.name,
        policy_types=["Ingress"],
        ingress=create_ip_block(
            ip_address=f"{random_ipv4_address(net_seed=0, host_address=123)}/{SPECIFIC_HOST_MASK}",
        ),
        client=admin_client,
    ) as mnp:
        yield mnp


@pytest.fixture()
def vmc_ingress_multi_network_policy(
    admin_client,
    flat_overlay_vmc_vmd_nad,
    vmc_domain_label,
    vmd_ingress_ip_block,
):
    with MultiNetworkPolicy(
        name="server-client-ingress-mnp",
        namespace=flat_overlay_vmc_vmd_nad.namespace,
        pod_selector={"matchLabels": vmc_domain_label},
        network_name=flat_overlay_vmc_vmd_nad.name,
        policy_types=["Ingress"],
        ingress=vmd_ingress_ip_block,
        client=admin_client,
    ) as mnp:
        yield mnp


@pytest.fixture(scope="class")
def vma_domain_label(vma_flat_overlay):
    return get_vm_kubevirt_domain_label(vm=vma_flat_overlay)


@pytest.fixture(scope="class")
def vmb_domain_label(vmb_flat_overlay):
    return get_vm_kubevirt_domain_label(vm=vmb_flat_overlay)


@pytest.fixture(scope="class")
def vmc_domain_label(vmc_flat_overlay):
    return get_vm_kubevirt_domain_label(vm=vmc_flat_overlay)


@pytest.fixture(scope="class")
def vmd_ingress_ip_block(flat_l2_port, vmd_flat_overlay_ip_address):
    ingress = create_ip_block(ip_address=f"{vmd_flat_overlay_ip_address}/{SPECIFIC_HOST_MASK}")
    ingress[0]["ports"] = [{"protocol": "TCP", "port": flat_l2_port}]
    return ingress


@pytest.fixture()
def vmc_nc_connection_initialization(flat_l2_port, vmc_flat_overlay):
    start_nc_response_on_vm(vm=vmc_flat_overlay, num_connections=CONNECTION_REQUESTS, flat_l2_port=flat_l2_port)


@pytest.fixture()
def vmd_connection_response(flat_l2_port, vmd_flat_overlay, vmc_flat_overlay_ip_address, flat_overlay_vmc_vmd_nad):
    assert (
        get_vm_connection_reply(source_vm=vmd_flat_overlay, dst_ip=vmc_flat_overlay_ip_address, port=flat_l2_port)
        == f"{HTTP_SUCCESS_RESPONSE_STR}-1"
    )
