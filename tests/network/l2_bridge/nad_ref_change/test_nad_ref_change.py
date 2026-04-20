"""
Live Update NetworkAttachmentDefinition Reference Tests — Linux Bridge

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/hotpluggable-nad-ref.md

Preconditions:
    - Two Linux bridge Network Attachment Definitions on different VLANs: NAD-VLAN-A, NAD-VLAN-B
    - Running reference VM with one bridge-bound interface connected to NAD-VLAN-A
      and one bridge-bound interface connected to NAD-VLAN-B
"""

import pytest


@pytest.mark.polarion("CNV-15945")
def test_bridge_binding_vlan_change_on_running_vm():
    """
    Test that a running VM with bridge binding can be reconnected to a new VLAN
    without rebooting.

    Preconditions:
        - Running under-test VM with a bridge-bound secondary interface connected to NAD-VLAN-A
        - TCP connectivity established between the under-test VM and the reference VM on NAD-VLAN-A

    Steps:
        1. Record the guest secondary interface MAC address, name, and IP addresses
        2. Update the under-test VM's secondary network to reference NAD-VLAN-B

    Expected:
        - Under-test VM remains running after the NAD reference change
        - Under-test VM eventually has TCP connectivity to the reference VM on NAD-VLAN-B
        - Under-test VM has no TCP connectivity to the reference VM on NAD-VLAN-A
        - Guest secondary interface MAC address, name, and IP addresses are the same before and after the
          NAD reference change
    """


test_bridge_binding_vlan_change_on_running_vm.__test__ = False


@pytest.mark.polarion("CNV-15946")
def test_multiple_secondary_networks_independently_updated():
    """
    Test that multiple secondary networks on the same running VM can each be
    independently updated to different NADs simultaneously.

    Preconditions:
        - Running under-test VM with two bridge-bound secondary interfaces:
          first interface connected to NAD-VLAN-A, second interface connected to NAD-VLAN-B
        - TCP connectivity established between the under-test VM first interface
          and the reference VM on NAD-VLAN-A
        - TCP connectivity established between the under-test VM second interface
          and the reference VM on NAD-VLAN-B

    Steps:
        1. Update both secondary networks of the under-test VM simultaneously:
           first interface to NAD-VLAN-B, second interface to NAD-VLAN-A

    Expected:
        - Under-test VM remains running after both NAD reference changes
        - Under-test VM first interface eventually has TCP connectivity to the reference VM on NAD-VLAN-B
        - Under-test VM second interface eventually has TCP connectivity to the reference VM on NAD-VLAN-A
    """


test_multiple_secondary_networks_independently_updated.__test__ = False


@pytest.mark.polarion("CNV-15947")
def test_non_migratable_vm_nad_change_not_applied():
    """
    [NEGATIVE] Test that changing the NAD reference on a non-migratable VM does not
    silently succeed — the VM remains connected to the original network.

    Preconditions:
        - Running non-migratable under-test VM with a bridge-bound secondary interface connected to NAD-VLAN-A
        - TCP connectivity established between the non-migratable under-test VM and the reference VM on NAD-VLAN-A

    Steps:
        1. Update the non-migratable under-test VM's secondary network to reference NAD-VLAN-B

    Expected:
        - Non-migratable under-test VM retains connectivity to the reference VM on NAD-VLAN-A
        - Non-migratable under-test VM has no connectivity to the reference VM on NAD-VLAN-B
    """


test_non_migratable_vm_nad_change_not_applied.__test__ = False
