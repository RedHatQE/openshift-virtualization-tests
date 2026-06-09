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

from libs.net.ip import filter_link_local_addresses
from libs.net.vmspec import lookup_iface_status
from tests.network.libs.connectivity import poll_tcp_connectivity
from tests.network.libs.nad_ref import update_nad_references
from tests.network.localnet.liblocalnet import (
    GUEST_1ST_IFACE_NAME,
    GUEST_2ND_IFACE_NAME,
    IFACE_A_NAME,
    IFACE_B_NAME,
)


@pytest.mark.usefixtures("nncp_localnet", "baseline_connectivity_localnet")
@pytest.mark.polarion("CNV-15948")
def test_running_vm_vlan_change(
    subtests,
    under_test_vm_localnet,
    ref_vm_localnet,
    cudn_nad_ref_vlan_b,
):
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
    update_nad_references(vm=under_test_vm_localnet, nad_name_by_net={IFACE_A_NAME: cudn_nad_ref_vlan_b.name})

    for server_ip in filter_link_local_addresses(
        ip_addresses=lookup_iface_status(vm=ref_vm_localnet, iface_name=IFACE_B_NAME).ipAddresses
    ):
        with subtests.test(msg=f"IPv{server_ip.version} connectivity on {IFACE_B_NAME}"):
            poll_tcp_connectivity(
                client_vm=under_test_vm_localnet,
                server_vm=ref_vm_localnet,
                server_ip=str(server_ip),
                server_bind_dev=GUEST_2ND_IFACE_NAME,
                client_bind_dev=GUEST_1ST_IFACE_NAME,
            )
    for server_ip in filter_link_local_addresses(
        ip_addresses=lookup_iface_status(vm=ref_vm_localnet, iface_name=IFACE_A_NAME).ipAddresses
    ):
        with subtests.test(msg=f"IPv{server_ip.version} no connectivity on {IFACE_A_NAME}"):
            poll_tcp_connectivity(
                client_vm=under_test_vm_localnet,
                server_vm=ref_vm_localnet,
                server_ip=str(server_ip),
                server_bind_dev=GUEST_1ST_IFACE_NAME,
                client_bind_dev=GUEST_1ST_IFACE_NAME,
                expect_connectivity=False,
            )
