"""
Live Update NetworkAttachmentDefinition Reference Tests — Localnet

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/hotpluggable-nad-ref.md

Preconditions:
    - Two localnet Network Attachment Definitions on different VLANs: NAD-VLAN-A, NAD-VLAN-B
    - Running reference VM with one bridge-bound interface connected to NAD-VLAN-A
      and one bridge-bound interface connected to NAD-VLAN-B
"""

import pytest


@pytest.mark.polarion("CNV-15948")
def test_localnet_secondary_network_vlan_change_on_running_vm():
    """
    Test that a running VM connected to a localnet secondary network can be
    reconnected to a different VLAN via a new localnet NAD without rebooting.

    Preconditions:
        - Running under-test VM with bridge binding connected to NAD-VLAN-A
        - TCP connectivity established between the under-test VM and the reference VM on NAD-VLAN-A

    Steps:
        1. Update the under-test VM's secondary network to reference NAD-VLAN-B

    Expected:
        - Under-test VM remains running after the NAD reference change
        - Under-test VM eventually has TCP connectivity to the reference VM on NAD-VLAN-B
        - Under-test VM has no TCP connectivity to the reference VM on NAD-VLAN-A
    """


test_localnet_secondary_network_vlan_change_on_running_vm.__test__ = False
