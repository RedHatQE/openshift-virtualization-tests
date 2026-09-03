"""
Primary UDN upgrade tests

Preconditions:
    - UDN namespace (with required annotations).
    - A primary UDN network.
"""

import os

import pytest

from libs.net.vmspec import lookup_primary_network
from tests.network.libs.connectivity import packet_loss_percent_from_ping_output, ping_between_vms
from tests.upgrade_params import (
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
)
from utilities.constants.pytest import DEPENDENCY_SCOPE_SESSION

BEFORE_UPGRADE_UDN_CONNECTIVITY_TEST_ID = (
    f"{os.path.abspath(__file__)}::test_connectivity_between_udn_vms_before_upgrade"
)

pytestmark = [
    pytest.mark.upgrade,
    pytest.mark.ocp_upgrade,
    pytest.mark.cnv_upgrade,
    pytest.mark.eus_upgrade,
    pytest.mark.single_nic,
]


@pytest.mark.polarion("CNV-13118")
def test_udn_vm_state_before_upgrade():
    """
    Test that a VM with:
    - A primary UDN network.
    - An explicit IP address specified.

    Can preserve its IP address over a cluster upgrade (VM is in running state).

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ip-request.md

    Preconditions:
        - Run before cluster upgrade.
        - Running under-test VM, with a primary UDN network and an IP address specified
            (through annotation & cloud-init).
        - The specified IP address on the under-test VM.

    Steps:
        1. Execute a ping command from the under-test VM to the external IP address.

    Expected:
        - IP address reported by VMI status and guest OS is the same as the one specified.
        - Ping command succeeds with 0% packet loss.
    """


test_udn_vm_state_before_upgrade.__test__ = False


@pytest.mark.ipv4
@pytest.mark.polarion("CNV-11617")
@pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
# Post-upgrade test depends on this to skip if pre-upgrade connectivity already fails.
@pytest.mark.dependency(name=BEFORE_UPGRADE_UDN_CONNECTIVITY_TEST_ID, scope=DEPENDENCY_SCOPE_SESSION)
def test_connectivity_between_udn_vms_before_upgrade(running_udn_vms_upgrade):
    """
    Test that two VMs with a primary UDN network can communicate with each other over IPv4.

    No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-94228 # <skip-jira-utils-check>

    Preconditions:
        - Run before cluster upgrade.
        - Two running under-test VMs, each with a primary UDN network.

    Steps:
        1. Execute a ping command from one under-test VM to the other under-test VM over IPv4.

    Expected:
        - Ping command succeeds with 0% packet loss.
    """
    source_vm, destination_vm = running_udn_vms_upgrade
    ping_output = ping_between_vms(
        source_vm=source_vm,
        destination_vm=destination_vm,
        iface_name=lookup_primary_network(vm=destination_vm).name,
    )
    packet_loss = packet_loss_percent_from_ping_output(ping_output=ping_output)
    assert packet_loss == 0, f"Ping over IPv4 before upgrade reported {packet_loss}% packet loss."


@pytest.mark.polarion("CNV-13119")
def test_udn_vm_state_after_upgrade():
    """
    Test that a VM with:
    - A primary UDN network.
    - An explicit IP address specified.

    Can preserve its IP address over a cluster upgrade (VM is in running state).

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ip-request.md

    Preconditions:
        - Run after cluster upgrade.
        - Running under-test VM, with a primary UDN network and an IP address specified
            (through annotation & cloud-init).
        - The specified IP address on the under-test VM.

    Steps:
        1. Execute a ping command from the under-test VM to the external IP address.

    Expected:
        - IP address reported by VMI status and guest OS is the same as the one specified.
        - Ping command succeeds with 0% packet loss.
    """


test_udn_vm_state_after_upgrade.__test__ = False


@pytest.mark.ipv4
@pytest.mark.polarion("CNV-16774")
@pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
# Requires upgrade completion and pre-upgrade baseline connectivity.
@pytest.mark.dependency(
    depends=[
        IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
        BEFORE_UPGRADE_UDN_CONNECTIVITY_TEST_ID,
    ],
    scope=DEPENDENCY_SCOPE_SESSION,
)
def test_connectivity_between_udn_vms_after_upgrade(running_udn_vms_upgrade):
    """
    Test that two VMs with a primary UDN network can communicate with each other over IPv4.

    No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-94228 # <skip-jira-utils-check>

    Preconditions:
        - Run after cluster upgrade.
        - Two running under-test VMs, each with a primary UDN network.

    Steps:
        1. Execute a ping command from one under-test VM to the other under-test VM over IPv4.

    Expected:
        - Ping command succeeds with 0% packet loss.
    """
    source_vm, destination_vm = running_udn_vms_upgrade
    ping_output = ping_between_vms(
        source_vm=source_vm,
        destination_vm=destination_vm,
        iface_name=lookup_primary_network(vm=destination_vm).name,
    )
    packet_loss = packet_loss_percent_from_ping_output(ping_output=ping_output)
    assert packet_loss == 0, f"Ping over IPv4 after upgrade reported {packet_loss}% packet loss."
