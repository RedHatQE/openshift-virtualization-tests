"""
Live Update NetworkAttachmentDefinition Reference Tests — Localnet

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/hotpluggable-nad-ref.md

Preconditions:
    - Two localnet Network Attachment Definitions on different VLANs: NAD-VLAN-A, NAD-VLAN-B
    - Running reference VM with one secondary localnet network connected to NAD-VLAN-A,
      and one secondary localnet network connected to NAD-VLAN-B
"""

import pytest


@pytest.mark.polarion("CNV-15948")
def test_running_vm_vlan_change():
    """
    Test that a running VM can change the VLAN of its secondary localnet network, without rebooting.
    The VM should establish TCP connectivity on the new VLAN.

    Preconditions:
        - Running under-test VM with a secondary localnet network connected to NAD-VLAN-A
        - TCP connectivity established between the under-test VM and the reference VM on NAD-VLAN-A
        - No TCP connectivity between the under-test VM and the reference VM on NAD-VLAN-B

    Steps:
        1. Update the under-test VM's secondary network to reference NAD-VLAN-B
        2. Wait for the change to be applied successfully (the update condition clears and the VM reaches synced status)

    Expected:
        - Under-test VM remains running after the NAD reference change
        - Under-test VM eventually has TCP connectivity to the reference VM on NAD-VLAN-B
        - Under-test VM has no TCP connectivity to the reference VM on NAD-VLAN-A
    """


test_running_vm_vlan_change.__test__ = False
