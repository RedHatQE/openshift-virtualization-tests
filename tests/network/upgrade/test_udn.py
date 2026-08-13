"""
Primary UDN upgrade tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ip-request.md

Markers:
    - upgrade
    - ocp_upgrade
    - cnv_upgrade
    - eus_upgrade
    - single_nic

Preconditions:
    - UDN namespace (with required annotations).
    - A primary UDN network.
    - A running VM with a primary UDN network and an explicit IP address specified.
"""

import pytest


@pytest.mark.polarion("CNV-13118")
def test_udn_vm_state_before_upgrade():
    """
    Test that a VM with:
    - A primary UDN network.
    - An explicit IP address specified.

    Can preserve its IP address over a cluster upgrade (VM is in running state).

    Preconditions:
        - Run before cluster upgrade.
        - Running under-test VM, with a primary UDN network and an IP address specified
            (through annotation & cloud-init).
        - The specified IP address on the under-test VM.

    Steps:
        1. Execute a ping command from the under-test VM to the external IP address.

    Expected:
        - IP address reported by VMI status and guest OS is the same as the one specified.
        - Verify that the ping command succeeds with 0% packet loss.
    """


test_udn_vm_state_before_upgrade.__test__ = False


@pytest.mark.polarion("CNV-13119")
def test_udn_vm_state_after_upgrade():
    """
    Test that a VM with:
    - A primary UDN network.
    - An explicit IP address specified.

    Can preserve its IP address over a cluster upgrade (VM is in running state).

    Preconditions:
        - Run after cluster upgrade.
        - Running under-test VM, with a primary UDN network and an IP address specified
            (through annotation & cloud-init).
        - The specified IP address on the under-test VM.

    Steps:
        1. Execute a ping command from the under-test VM to the external IP address.

    Expected:
        - IP address reported by VMI status and guest OS is the same as the one specified.
        - Verify that the ping command succeeds with 0% packet loss.
    """


test_udn_vm_state_after_upgrade.__test__ = False
