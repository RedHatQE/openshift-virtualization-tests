# -*- coding: utf-8 -*-
"""
Network Migration test
"""

import logging
import re
import shlex

import pytest
from ocp_resources.service import Service
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutSampler

from tests.network.utils import (
    assert_ssh_alive,
    run_ssh_in_background,
    vm_for_brcnv_tests,
)
from utilities.constants import (
    IP_FAMILY_POLICY_PREFER_DUAL_STACK,
    IPV6_STR,
    LINUX_BRIDGE,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
)
from utilities.infra import get_node_selector_dict
from utilities.network import (
    assert_ping_successful,
    compose_cloud_init_data_dict,
    get_valid_ip_address,
    get_vmi_ip_v4_by_name,
    network_device,
    network_nad,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
)

PING_LOG = "ping.log"
LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.usefixtures("hyperconverged_ovs_annotations_enabled_scope_session")


def http_port_accessible(vm, server_ip, server_port):
    if get_valid_ip_address(family=IPV6_STR, dst_ip=server_ip):
        server_ip = f"'[{server_ip}]'"

    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=5,
        func=run_ssh_commands,
        host=vm.ssh_exec,
        commands=[shlex.split(f"curl --head {server_ip}:{server_port}")],
    )
    for sample in sampler:
        if sample:
            return


@pytest.fixture(scope="module")
def bridge_worker_1(
    worker_node1,
    nodes_available_nics,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="migration-worker-1",
        interface_name="migration-br",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.name][-1]],
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_worker_2(
    worker_node2,
    nodes_available_nics,
    bridge_worker_1,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="migration-worker-2",
        interface_name=bridge_worker_1.bridge_name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[nodes_available_nics[worker_node2.name][-1]],
    ) as br:
        yield br


@pytest.fixture(scope="module")
def br1test_nad(namespace, bridge_worker_1, bridge_worker_2):
    with network_nad(
        nad_type=bridge_worker_1.bridge_type,
        nad_name="network-migration-nad",
        interface_name=bridge_worker_1.bridge_name,
        namespace=namespace,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def vma(
    namespace,
    unprivileged_client,
    cpu_for_migration,
    dual_stack_network_data,
    br1test_nad,
):
    name = "vma"
    networks = {br1test_nad.name: br1test_nad.name}
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.1/24"]}}}
    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
        ipv6_network_data=dual_stack_network_data,
    )
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
        cpu_model=cpu_for_migration,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def vmb(
    namespace,
    unprivileged_client,
    cpu_for_migration,
    dual_stack_network_data,
    br1test_nad,
):
    name = "vmb"
    networks = {br1test_nad.name: br1test_nad.name}
    network_data_data = {"ethernets": {"eth1": {"addresses": ["10.200.0.2/24"]}}}
    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
        ipv6_network_data=dual_stack_network_data,
    )

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
        cpu_model=cpu_for_migration,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def brcnv_vm_for_migration(
    unprivileged_client,
    namespace,
    brcnv_ovs_nad_vlan_1,
):
    yield from vm_for_brcnv_tests(
        vm_name="migration-vm",
        namespace=namespace,
        unprivileged_client=unprivileged_client,
        nads=[brcnv_ovs_nad_vlan_1],
        address_suffix=4,
    )


@pytest.fixture(scope="module")
def running_vma(vma):
    return running_vm(vm=vma, wait_for_cloud_init=True)


@pytest.fixture(scope="module")
def running_vmb(vmb):
    return running_vm(vm=vmb, wait_for_cloud_init=True)


@pytest.fixture()
def restarted_vmb(running_vmb):
    restart_vm_wait_for_running_vm(vm=running_vmb, check_ssh_connectivity=False)


@pytest.fixture(scope="module")
def http_service(namespace, running_vma, running_vmb):
    running_vmb.custom_service_enable(
        service_name="http-masquerade-migration",
        port=80,
        service_type=Service.Type.CLUSTER_IP,
        ip_family_policy=IP_FAMILY_POLICY_PREFER_DUAL_STACK,
    )
    LOGGER.info(f"HTTP service was created on node {running_vmb.vmi.node.name}")

    # Check that http service on port 80 can be accessed by all cluster IPs
    # before vmi migration.
    for server_ip in running_vmb.custom_service.instance.spec.clusterIPs:
        http_port_accessible(
            vm=running_vma,
            server_ip=server_ip,
            server_port=running_vmb.custom_service.service_port,
        )


@pytest.fixture(scope="module")
def ping_in_background(br1test_nad, running_vma, running_vmb):
    dst_ip = get_vmi_ip_v4_by_name(vm=running_vmb, name=br1test_nad.name)
    assert_ping_successful(src_vm=running_vma, dst_ip=dst_ip)
    LOGGER.info(f"Ping {dst_ip} from {running_vma.name} to {running_vmb.name}")
    run_ssh_commands(
        host=running_vma.ssh_exec,
        commands=[shlex.split(f"sudo ping -i 0.1 {dst_ip} >& {PING_LOG} &")],
    )


# custom exception for using xfail in test_ping_vm_migration
class HighPacketLossError(Exception):
    pass


def assert_low_packet_loss(vm):
    output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            shlex.split("sudo kill -SIGINT `pgrep ping`"),
            shlex.split(f"cat {PING_LOG}"),
        ],
    )
    packet_loss = re.findall(r"\d+.\d+% packet loss", output[1])
    assert packet_loss
    float_packet_loss = float(re.findall(r"\d+.\d+", packet_loss[0])[0])
    if float_packet_loss > 2:
        LOGGER.error(f"Current packet loss is {float_packet_loss}% (greater than 2%!)")
        raise HighPacketLossError


@pytest.fixture(scope="module")
def ssh_in_background(br1test_nad, running_vma, running_vmb):
    """
    Start ssh connection to the vm
    """
    run_ssh_in_background(
        nad=br1test_nad,
        src_vm=running_vma,
        dst_vm=running_vmb,
        dst_vm_user=running_vmb.login_params["username"],
        dst_vm_password=running_vmb.login_params["password"],
    )


@pytest.fixture()
def brcnv_ssh_in_background(brcnv_ovs_nad_vlan_1, brcnv_vma_with_vlan_1, brcnv_vm_for_migration):
    """
    Start ssh connection to the vm
    """

    run_ssh_in_background(
        nad=brcnv_ovs_nad_vlan_1,
        src_vm=brcnv_vma_with_vlan_1,
        dst_vm=brcnv_vm_for_migration,
        dst_vm_user=brcnv_vm_for_migration.login_params["username"],
        dst_vm_password=brcnv_vm_for_migration.login_params["password"],
    )


@pytest.fixture(scope="module")
def migrated_vmb_and_wait_for_success(running_vmb, http_service):
    migrate_vm_and_verify(
        vm=running_vmb,
    )


@pytest.fixture(scope="module")
def vma_ip_address(br1test_nad, running_vma):
    return get_vmi_ip_v4_by_name(vm=running_vma, name=br1test_nad.name)


@pytest.fixture(scope="module")
def migrated_vmb_without_waiting_for_success(vma_ip_address, running_vmb, br1test_nad):
    """
    1. Assert ping is successful before migrating vmb.
    2. Migrate vmb without waiting for success. As soon as the VMI acquire a new IP address, return.
    Since the wait_for_migration_success in the migration is set to false, migrate_vm_and_verify will not delete the
    migration object.
    """
    assert_ping_successful(src_vm=running_vmb, dst_ip=vma_ip_address, count=10)
    vmb_ip_before_migration = running_vmb.vmi.interfaces[0]["ipAddress"]
    migrated_vmi = migrate_vm_and_verify(vm=running_vmb, wait_for_migration_success=False)
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=1,
        func=lambda: vmb_ip_before_migration != running_vmb.vmi.interfaces[0]["ipAddress"],
    ):
        if sample:
            break
    yield
    migrated_vmi.clean_up()


@pytest.fixture()
def brcnv_migrated_vm(
    brcnv_vm_for_migration,
):
    migrate_vm_and_verify(vm=brcnv_vm_for_migration)


@pytest.mark.xfail(
    reason=(
        "Network infrastructure is slow from time to time. "
        "Due to that, test might fail with packet loss greater than 2%"
    ),
    raises=HighPacketLossError,
)
@pytest.mark.ipv4
@pytest.mark.polarion("CNV-2060")
def test_ping_vm_migration(
    vma,
    vmb,
    running_vma,
    running_vmb,
    ping_in_background,
    migrated_vmb_and_wait_for_success,
):
    assert_low_packet_loss(vm=running_vma)


@pytest.mark.ipv4
@pytest.mark.polarion("CNV-2063")
def test_ssh_vm_migration(
    namespace,
    br1test_nad,
    vma,
    vmb,
    running_vma,
    running_vmb,
    ssh_in_background,
    migrated_vmb_and_wait_for_success,
):
    src_ip = str(get_vmi_ip_v4_by_name(vm=running_vma, name=br1test_nad.name))
    assert_ssh_alive(ssh_vm=running_vma, src_ip=src_ip)


@pytest.mark.ovs_brcnv
@pytest.mark.ipv4
@pytest.mark.polarion("CNV-8600")
def test_cnv_bridge_ssh_vm_migration(
    brcnv_ovs_nad_vlan_1,
    brcnv_vma_with_vlan_1,
    brcnv_vm_for_migration,
    brcnv_ssh_in_background,
    brcnv_migrated_vm,
):
    src_ip = str(get_vmi_ip_v4_by_name(vm=brcnv_vma_with_vlan_1, name=brcnv_ovs_nad_vlan_1.name))
    assert_ssh_alive(ssh_vm=brcnv_vma_with_vlan_1, src_ip=src_ip)


@pytest.mark.post_upgrade
@pytest.mark.ipv4
@pytest.mark.polarion("CNV-5565")
def test_connectivity_after_migration_and_restart(
    namespace,
    br1test_nad,
    vma,
    vmb,
    running_vma,
    running_vmb,
    restarted_vmb,
):
    assert_ping_successful(
        src_vm=running_vma,
        dst_ip=get_vmi_ip_v4_by_name(vm=running_vmb, name=br1test_nad.name),
    )


@pytest.mark.polarion("CNV-2061")
def test_migration_with_masquerade(
    ip_stack_version_matrix__module__,
    admin_client,
    skip_if_not_ipv4_supported_cluster_from_mtx,
    skip_if_not_ipv6_supported_cluster_from_mtx,
    vma,
    vmb,
    running_vma,
    running_vmb,
    migrated_vmb_and_wait_for_success,
):
    LOGGER.info(f"Testing HTTP service after migration on node {running_vmb.vmi.node.name}")
    http_port_accessible(
        vm=running_vma,
        server_ip=running_vmb.custom_service.service_ip(ip_family=ip_stack_version_matrix__module__),
        server_port=running_vmb.custom_service.service_port,
    )


@pytest.mark.ipv4
@pytest.mark.polarion("CNV-6548")
def test_ping_from_migrated_vm(
    br1test_nad,
    vma,
    vmb,
    running_vma,
    running_vmb,
    vma_ip_address,
    migrated_vmb_without_waiting_for_success,
):
    assert_ping_successful(src_vm=running_vmb, dst_ip=vma_ip_address, count=10)
