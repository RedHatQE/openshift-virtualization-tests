"""
Primary UDN upgrade tests

Markers:
    - upgrade
    - ocp_upgrade
    - cnv_upgrade
    - eus_upgrade
    - single_nic

Preconditions:
    - UDN namespace (with required annotations).
    - A primary UDN network.
"""

import pytest


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


@pytest.mark.polarion("CNV-11617")
def test_connectivity_between_udn_vms_before_upgrade():
    """
    Test that two VMs with a primary UDN network can communicate with each other over the primary UDN network.

    No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-94228 # <skip-jira-utils-check>

    Preconditions:
        - Run before cluster upgrade.
        - Two running under-test VMs, each with a primary UDN network.

    Steps:
        1. Execute a ping command from one under-test VM to the other under-test VM.

    Expected:
        - Ping command succeeds with 0% packet loss.
    """


test_connectivity_between_udn_vms_before_upgrade.__test__ = False


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


@pytest.mark.polarion("CNV-16774")
def test_connectivity_between_udn_vms_after_upgrade():
    """
    Test that two VMs with a primary UDN network can communicate with each other over the primary UDN network.

    No STP exists for this scenario - tracked via Jira: https://redhat.atlassian.net/browse/CNV-94228 # <skip-jira-utils-check>

    Preconditions:
        - Run after cluster upgrade.
        - Two running under-test VMs, each with a primary UDN network.

    Steps:
        1. Execute a ping command from one under-test VM to the other under-test VM.

    Expected:
        - Ping command succeeds with 0% packet loss.
    """


test_connectivity_between_udn_vms_after_upgrade.__test__ = False
