from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.net.ip import filter_link_local_addresses, random_cidr_addresses_by_family
from libs.net.netattachdef import NetworkAttachmentDefinition
from libs.net.vmspec import lookup_iface_status, wait_for_ifaces_status
from libs.vm.vm import BaseVirtualMachine
from tests.network.l2_bridge.libl2bridge import LINUX_BRIDGE_IFACE_NAME_1, LINUX_BRIDGE_IFACE_NAME_2
from tests.network.l2_bridge.nad_ref_change.lib_helpers import (
    GUEST_IFACE_1,
    GUEST_IFACE_2,
    NET_SEED,
    two_secondary_bridge_vm,
)
from tests.network.libs.connectivity import ARP_ISOLATION_SYSCTL_CMD, poll_tcp_connectivity


@pytest.fixture(scope="module")
def ref_vm(
    namespace: Namespace,
    unprivileged_client: DynamicClient,
    bridge_nad_a: NetworkAttachmentDefinition,
    bridge_nad_b: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    iface_a_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=1)
    iface_b_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=2)
    with two_secondary_bridge_vm(
        namespace=namespace.name,
        name="ref-vm",
        client=unprivileged_client,
        nad_names=[bridge_nad_a.name, bridge_nad_b.name],
        ip_addresses=[iface_a_ips, iface_b_ips],
        iface_names=[LINUX_BRIDGE_IFACE_NAME_1, LINUX_BRIDGE_IFACE_NAME_2],
        runcmd=ARP_ISOLATION_SYSCTL_CMD,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                LINUX_BRIDGE_IFACE_NAME_1: [addr.split("/")[0] for addr in iface_a_ips],
                LINUX_BRIDGE_IFACE_NAME_2: [addr.split("/")[0] for addr in iface_b_ips],
            },
        )
        yield vm


@pytest.fixture(scope="class")
def under_test_vm_two_ifaces(
    namespace: Namespace,
    unprivileged_client: DynamicClient,
    bridge_nad_a: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    iface_a_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=3)
    iface_b_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=4)
    with two_secondary_bridge_vm(
        namespace=namespace.name,
        name="under-test-vm-two-ifaces",
        client=unprivileged_client,
        nad_names=[bridge_nad_a.name, bridge_nad_a.name],
        ip_addresses=[iface_a_ips, iface_b_ips],
        iface_names=[LINUX_BRIDGE_IFACE_NAME_1, LINUX_BRIDGE_IFACE_NAME_2],
        runcmd=ARP_ISOLATION_SYSCTL_CMD,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                LINUX_BRIDGE_IFACE_NAME_1: [addr.split("/")[0] for addr in iface_a_ips],
                LINUX_BRIDGE_IFACE_NAME_2: [addr.split("/")[0] for addr in iface_b_ips],
            },
        )
        yield vm


@pytest.fixture(scope="class")
def baseline_connectivity(
    under_test_vm_two_ifaces: BaseVirtualMachine,
    ref_vm: BaseVirtualMachine,
) -> None:
    """Verify baseline connectivity before the NAD reference change.

    Asserts that the under-test VM can reach the reference VM on VLAN-A (iface-1)
    and cannot reach it on VLAN-B (iface-2) before any NAD update is applied.
    """
    for server_ip in filter_link_local_addresses(
        ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=LINUX_BRIDGE_IFACE_NAME_1).ipAddresses
    ):
        poll_tcp_connectivity(
            client_vm=under_test_vm_two_ifaces,
            server_vm=ref_vm,
            server_ip=str(server_ip),
            server_bind_dev=GUEST_IFACE_1,
        )
    for server_ip in filter_link_local_addresses(
        ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=LINUX_BRIDGE_IFACE_NAME_2).ipAddresses
    ):
        poll_tcp_connectivity(
            client_vm=under_test_vm_two_ifaces,
            server_vm=ref_vm,
            server_ip=str(server_ip),
            server_bind_dev=GUEST_IFACE_2,
            expect_connectivity=False,
        )
