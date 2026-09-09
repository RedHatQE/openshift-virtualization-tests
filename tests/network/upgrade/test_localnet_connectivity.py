"""
Localnet connectivity upgrade tests.

Verifies IPAM-less localnet VM connectivity is preserved across cluster upgrades,
for both default bridge (br-ex) and dedicated NIC bridge.
https://redhat.atlassian.net/browse/CNV-85783  # <skip-jira-utils-check>

Preconditions:
    - OVN bridge mapping configured via NNCP for the default bridge (br-ex)
    - OVS bridge mapping configured via NNCP on a secondary NIC available on all worker nodes
    - IPAM-less localnet CUDNs configured for both default bridge and dedicated NIC bridge
    - Two running VMs on different nodes with static IPs on both localnet interfaces
"""

import os

import pytest

from libs.net.ip import filter_link_local_addresses
from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from libs.net.vmspec import lookup_iface_status
from tests.network.libs.localnet import LOCALNET_BR_EX_INTERFACE, LOCALNET_OVS_BRIDGE_INTERFACE
from tests.upgrade_params import (
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
)
from utilities.constants.pytest import DEPENDENCY_SCOPE_SESSION

BEFORE_UPGRADE_DEFAULT_BRIDGE_TEST_ID = (
    f"{os.path.abspath(__file__)}::test_default_bridge_localnet_connectivity_before_upgrade"
)
BEFORE_UPGRADE_DEDICATED_NIC_BRIDGE_TEST_ID = (
    f"{os.path.abspath(__file__)}::test_dedicated_nic_bridge_localnet_connectivity_before_upgrade"
)

pytestmark = [
    pytest.mark.upgrade,
    pytest.mark.ocp_upgrade,
    pytest.mark.cnv_upgrade,
    pytest.mark.eus_upgrade,
]


@pytest.mark.polarion("CNV-16258")
@pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
# Post-upgrade test depends on this to skip if pre-upgrade connectivity already fails.
@pytest.mark.dependency(name=BEFORE_UPGRADE_DEFAULT_BRIDGE_TEST_ID, scope=DEPENDENCY_SCOPE_SESSION)
def test_default_bridge_localnet_connectivity_before_upgrade(subtests, localnet_running_vms_upgrade):
    """
    Preconditions:
        - Two running VMs on different nodes with static IPs on localnet

    Steps:
        1. Establish TCP connection between the VMs over localnet.

    Expected:
        - TCP connection succeeds.
    """
    vm_a, vm_b = localnet_running_vms_upgrade
    iface = lookup_iface_status(vm=vm_b, iface_name=LOCALNET_BR_EX_INTERFACE)
    for dst_ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
        with subtests.test(msg=f"IPv{dst_ip.version}"):
            with client_server_active_connection(
                client_vm=vm_a,
                server_vm=vm_b,
                spec_logical_network=LOCALNET_BR_EX_INTERFACE,
                ip_family=dst_ip.version,
            ) as (client, server):
                assert is_tcp_connection(server=server, client=client)


@pytest.mark.polarion("CNV-16332")
@pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
# Post-upgrade test depends on this to skip if pre-upgrade connectivity already fails.
@pytest.mark.dependency(name=BEFORE_UPGRADE_DEDICATED_NIC_BRIDGE_TEST_ID, scope=DEPENDENCY_SCOPE_SESSION)
def test_dedicated_nic_bridge_localnet_connectivity_before_upgrade(subtests, localnet_running_vms_upgrade):
    """
    Preconditions:
        - Two running VMs on different nodes with static IPs on localnet over dedicated NIC bridge

    Steps:
        1. Establish TCP connection between the VMs over localnet.

    Expected:
        - TCP connection succeeds.
    """
    vm_a, vm_b = localnet_running_vms_upgrade
    iface = lookup_iface_status(vm=vm_b, iface_name=LOCALNET_OVS_BRIDGE_INTERFACE)
    for dst_ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
        with subtests.test(msg=f"IPv{dst_ip.version}"):
            with client_server_active_connection(
                client_vm=vm_a,
                server_vm=vm_b,
                spec_logical_network=LOCALNET_OVS_BRIDGE_INTERFACE,
                ip_family=dst_ip.version,
            ) as (client, server):
                assert is_tcp_connection(server=server, client=client)


@pytest.mark.polarion("CNV-16259")
@pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
# Requires upgrade completion and pre-upgrade baseline connectivity.
@pytest.mark.dependency(
    depends=[
        IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
        BEFORE_UPGRADE_DEFAULT_BRIDGE_TEST_ID,
    ],
    scope=DEPENDENCY_SCOPE_SESSION,
)
def test_default_bridge_localnet_connectivity_after_upgrade(subtests, localnet_running_vms_upgrade):
    """
    Preconditions:
        - Cluster upgraded successfully
        - Two running VMs on different nodes with static IPs on localnet

    Steps:
        1. Establish TCP connection between the VMs over localnet.

    Expected:
        - TCP connection succeeds, connectivity preserved after upgrade.
    """
    vm_a, vm_b = localnet_running_vms_upgrade
    iface = lookup_iface_status(vm=vm_b, iface_name=LOCALNET_BR_EX_INTERFACE)
    for dst_ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
        with subtests.test(msg=f"IPv{dst_ip.version}"):
            with client_server_active_connection(
                client_vm=vm_a,
                server_vm=vm_b,
                spec_logical_network=LOCALNET_BR_EX_INTERFACE,
                ip_family=dst_ip.version,
            ) as (client, server):
                assert is_tcp_connection(server=server, client=client)


@pytest.mark.polarion("CNV-16333")
@pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
# Requires upgrade completion and pre-upgrade baseline connectivity.
@pytest.mark.dependency(
    depends=[
        IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
        BEFORE_UPGRADE_DEDICATED_NIC_BRIDGE_TEST_ID,
    ],
    scope=DEPENDENCY_SCOPE_SESSION,
)
def test_dedicated_nic_bridge_localnet_connectivity_after_upgrade(subtests, localnet_running_vms_upgrade):
    """
    Preconditions:
        - Cluster upgraded successfully
        - Two running VMs on different nodes with static IPs on localnet over dedicated NIC bridge

    Steps:
        1. Establish TCP connection between the VMs over localnet.

    Expected:
        - TCP connection succeeds, connectivity preserved after upgrade.
    """
    vm_a, vm_b = localnet_running_vms_upgrade
    iface = lookup_iface_status(vm=vm_b, iface_name=LOCALNET_OVS_BRIDGE_INTERFACE)
    for dst_ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses):
        with subtests.test(msg=f"IPv{dst_ip.version}"):
            with client_server_active_connection(
                client_vm=vm_a,
                server_vm=vm_b,
                spec_logical_network=LOCALNET_OVS_BRIDGE_INTERFACE,
                ip_family=dst_ip.version,
            ) as (client, server):
                assert is_tcp_connection(server=server, client=client)
