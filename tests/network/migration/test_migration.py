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

from libs.net.vmspec import lookup_iface_status_ip
from tests.network.libs.ip import random_ipv4_address
from tests.network.utils import (
    assert_ssh_alive,
    run_ssh_in_background,
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
    network_device,
    network_nad,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
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
    admin_client,
    worker_node1,
    hosts_common_available_ports,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="migration-worker-1",
        interface_name="migration-br",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[hosts_common_available_ports[-1]],
        client=admin_client,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_worker_2(
    admin_client,
    worker_node2,
    hosts_common_available_ports,
    bridge_worker_1,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="migration-worker-2",
        interface_name=bridge_worker_1.bridge_name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[hosts_common_available_ports[-1]],
        client=admin_client,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def br1test_nad(admin_client, namespace, bridge_worker_1, bridge_worker_2):
    with network_nad(
        nad_type=bridge_worker_1.bridge_type,
        nad_name="network-migration-nad",
        interface_name=bridge_worker_1.bridge_name,
        namespace=namespace,
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def vma(
    namespace,
    unprivileged_client,
    cpu_for_migration,
    ipv6_primary_interface_cloud_init_data,
    br1test_nad,
):
    name = "vma"
    networks = {br1test_nad.name: br1test_nad.name}
    network_data_data = {
        "ethernets": {"eth1": {"addresses": [f"{random_ipv4_address(net_seed=0, host_address=1)}/24"]}}
    }
    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
        ipv6_network_data=ipv6_primary_interface_cloud_init_data,
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
    ipv6_primary_interface_cloud_init_data,
    br1test_nad,
):
    name = "vmb"
    networks = {br1test_nad.name: br1test_nad.name}
    network_data_data = {
        "ethernets": {"eth1": {"addresses": [f"{random_ipv4_address(net_seed=0, host_address=2)}/24"]}}
    }
    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
        ipv6_network_data=ipv6_primary_interface_cloud_init_data,
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
def running_vma(vma):
    vma.wait_for_agent_connected()
    return vma


@pytest.fixture(scope="module")
def running_vmb(vmb):
    vmb.wait_for_agent_connected()
    return vmb


@pytest.fixture()
def restarted_vmb(running_vmb):
    running_vmb.restart(wait=True)
    running_vmb.wait_for_agent_connected()


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
    dst_ip = lookup_iface_status_ip(vm=running_vmb, iface_name=br1test_nad.name, ip_family=4)
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


@pytest.fixture(scope="module")
def migrated_vmb_and_wait_for_success(running_vmb, http_service):
    migrate_vm_and_verify(
        vm=running_vmb,
    )


@pytest.fixture(scope="module")
def vma_ip_address(br1test_nad, running_vma):
    return lookup_iface_status_ip(vm=running_vma, iface_name=br1test_nad.name, ip_family=4)


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


@pytest.mark.xfail(
    reason=(
        "Network infrastructure is slow from time to time. "
        "Due to that, test might fail with packet loss greater than 2%"
    ),
    raises=HighPacketLossError,
)
@pytest.mark.ipv4
@pytest.mark.polarion("CNV-2060")
@pytest.mark.s390x
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
@pytest.mark.s390x
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
    src_ip = str(lookup_iface_status_ip(vm=running_vma, iface_name=br1test_nad.name, ip_family=4))
    assert_ssh_alive(ssh_vm=running_vma, src_ip=src_ip)


@pytest.mark.post_upgrade
@pytest.mark.ipv4
@pytest.mark.polarion("CNV-5565")
@pytest.mark.s390x
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
        dst_ip=lookup_iface_status_ip(vm=running_vmb, iface_name=br1test_nad.name, ip_family=4),
    )


@pytest.mark.s390x
@pytest.mark.usefixtures("http_service", "migrated_vmb_and_wait_for_success")
@pytest.mark.parametrize(
    "ip_family",
    [
        pytest.param("ipv4", marks=[pytest.mark.ipv4, pytest.mark.polarion("CNV-12508")]),
        pytest.param("ipv6", marks=[pytest.mark.ipv6, pytest.mark.polarion("CNV-12509")]),
    ],
)
def test_migration_with_masquerade(
    running_vma,
    running_vmb,
    ip_family,
):
    http_port_accessible(
        vm=running_vma,
        server_ip=running_vmb.custom_service.service_ip(ip_family=ip_family),
        server_port=running_vmb.custom_service.service_port,
    )


@pytest.mark.ipv4
@pytest.mark.polarion("CNV-6548")
@pytest.mark.s390x
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
