from ipaddress import ip_interface

import pytest

from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.net.vmspec import lookup_iface_status
from tests.network.libs.ip import filter_link_local_addresses
from tests.network.localnet.liblocalnet import (
    GUEST_2ND_IFACE_NAME,
    LOCALNET_BR_EX_INTERFACE,
    LOCALNET_BR_EX_INTERFACE_NO_VLAN,
)
from utilities.constants import QUARANTINED
from utilities.virt import migrate_vm_and_verify


@pytest.mark.gating
@pytest.mark.single_nic
@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet")
@pytest.mark.polarion("CNV-11775")
def test_connectivity_over_migration_between_localnet_vms(
    subtests,
    localnet_running_vms,
    localnet_active_connections,
):
    _, client_vm = localnet_running_vms
    migrate_vm_and_verify(vm=client_vm)
    for dst_ip, server, client in localnet_active_connections:
        with subtests.test(msg=f"IPv{dst_ip.version}"):
            assert is_tcp_connection(server=server, client=client)


@pytest.mark.single_nic
@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet")
@pytest.mark.polarion("CNV-12363")
@pytest.mark.xfail(
    reason=f"{QUARANTINED}: The requested IPv6 address is assigned but not visible in VMI: CNV-80582",
    run=False,
)
def test_vmi_reports_ip_on_secondary_interface_without_vlan(
    localnet_running_vms,
):
    """
    Test that vm_localnet_1's secondary interface on a no-VLAN localnet
    correctly reports the IP addresses for that interface based on cluster network stack.
    """
    vm, _ = localnet_running_vms

    expected_ips = {ip_interface(addr).ip for addr in vm.cloud_init_iface_addresses(iface_name=GUEST_2ND_IFACE_NAME)}
    iface_status = lookup_iface_status(
        vm=vm,
        iface_name=LOCALNET_BR_EX_INTERFACE_NO_VLAN,
        predicate=lambda interface: (
            set(
                filter_link_local_addresses(
                    ip_addresses=[str(ip_interface(addr).ip) for addr in interface["ipAddresses"]]
                )
            )
            == expected_ips
        ),
    )
    reported_ips = set(
        filter_link_local_addresses(ip_addresses=[str(ip_interface(addr).ip) for addr in iface_status.ipAddresses])
    )
    assert reported_ips == expected_ips


@pytest.mark.single_nic
@pytest.mark.s390x
@pytest.mark.usefixtures("nncp_localnet")
@pytest.mark.polarion("CNV-11925")
def test_connectivity_post_migration_between_localnet_vms(
    subtests,
    migrated_localnet_vm,
    localnet_running_vms,
):
    vms = list(localnet_running_vms)
    vms.remove(migrated_localnet_vm)
    (base_localnet_vm,) = vms

    iface = lookup_iface_status(vm=migrated_localnet_vm, iface_name=LOCALNET_BR_EX_INTERFACE)
    for dst_ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
        with subtests.test(msg=f"IPv{dst_ip.version}"):
            with client_server_active_connection(
                client_vm=base_localnet_vm,
                server_vm=migrated_localnet_vm,
                spec_logical_network=LOCALNET_BR_EX_INTERFACE,
                port=8888,
                ip_family=dst_ip.version,
            ) as (client, server):
                assert is_tcp_connection(server=server, client=client)
