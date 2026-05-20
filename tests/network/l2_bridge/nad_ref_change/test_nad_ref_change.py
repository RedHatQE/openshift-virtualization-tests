"""
Live Update NetworkAttachmentDefinition Reference Tests — Linux Bridge

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/hotpluggable-nad-ref.md

Preconditions:
    - Two Network Attachment Definitions that define the same Linux bridge, each set to use a
      different VLAN: NAD-VLAN-A, NAD-VLAN-B.
    - Running reference VM with two secondary Linux bridge networks: one connected to NAD-VLAN-A,
      one connected to NAD-VLAN-B
"""

import pytest

from libs.net.ip import filter_link_local_addresses
from libs.net.vmspec import lookup_iface_status
from tests.network.l2_bridge.nad_ref_change.lib_helpers import (
    GUEST_IFACE_1,
    GUEST_IFACE_2,
    VM_IFACE_1,
    VM_IFACE_2,
    iface_info,
)
from tests.network.libs.connectivity import (
    poll_tcp_connectivity,
    update_nad_references,
)


@pytest.mark.incremental
class TestRunningVMLinuxBridgeVlanChange:
    """
    Tests for a running VM changing the VLAN of its secondary Linux bridge network(s) without rebooting.
    The VM should establish TCP connectivity on the new VLAN.

    Network state across the class tests:

        Initial (both ifaces on VLAN-A):
            Under-test VM             Reference VM
            +-----------+             +-----------+
            |  iface-1  |\\           |           |
            |           | >--VLAN-A --|  iface-1  |
            |  iface-2  |/            |  iface-2  |
            +-----------+             +-----------+

        After first test (iface-1: VLAN-A -> VLAN-B):
            Under-test VM             Reference VM
            +-----------+             +-----------+
            |  iface-1  |---VLAN-B -->|  iface-2  |
            |  iface-2  |---VLAN-A -->|  iface-1  |
            +-----------+             +-----------+

        After third test (iface-1: VLAN-B -> VLAN-A, iface-2: VLAN-A -> VLAN-B):
            Under-test VM             Reference VM
            +-----------+             +-----------+
            |  iface-1  |---VLAN-A -->|  iface-1  |
            |  iface-2  |---VLAN-B -->|  iface-2  |
            +-----------+             +-----------+

    Preconditions:
        - Running under-test VM with two secondary Linux bridge networks:
          both networks connected to NAD-VLAN-A
        - TCP connectivity established between the under-test VM first secondary network
          and the reference VM on NAD-VLAN-A
        - No TCP connectivity between the under-test VM and the reference VM on NAD-VLAN-B
    """

    @pytest.mark.polarion("CNV-15945")
    def test_vm_state_iface_info_preserved(
        self,
        under_test_vm_two_ifaces,
        bridge_nad_a,
        bridge_nad_b,
    ):
        """
        Test that the under-test VM remains running and its secondary network metadata is unchanged
        after the NAD reference change.

        Preconditions:
            - Running under-test VM with two secondary Linux bridge networks:
              both networks connected to NAD-VLAN-A

        Steps:
            1. Record the guest first secondary interface MAC address, name, and IP addresses
            2. Update the under-test VM's first secondary network to reference NAD-VLAN-B
            3. Wait for the change to be applied successfully (the update condition clears and the
               VM reaches synced status)

        Expected:
            - Under-test VM remains running after the NAD reference change
            - Guest first secondary interface MAC address, name, and IP addresses are the same before and after the
              NAD reference change
        """
        iface_before = iface_info(vm=under_test_vm_two_ifaces, iface_name=VM_IFACE_1)

        update_nad_references(vm=under_test_vm_two_ifaces, updates={VM_IFACE_1: bridge_nad_b.name})
        under_test_vm_two_ifaces.wait_for_ready_status(status=True)

        iface_after = iface_info(vm=under_test_vm_two_ifaces, iface_name=VM_IFACE_1)
        assert iface_after == iface_before, (
            f"Interface info changed after NAD reference update: before={iface_before}, after={iface_after}"
        )

    @pytest.mark.polarion("CNV-15972")
    def test_connectivity(
        self,
        subtests,
        under_test_vm_two_ifaces,
        bridge_nad_a,
        bridge_nad_b,
        ref_vm,
    ):
        """
        Test that the under-test VM has TCP connectivity to the reference VM on the new NAD-VLAN-B and no TCP
        connectivity on the old NAD-VLAN-A after the NAD reference change.

        Preconditions:
            - Running under-test VM with first secondary Linux bridge network connected to NAD-VLAN-B
            - Running reference VM with secondary Linux bridge networks connected to NAD-VLAN-A and NAD-VLAN-B

        Steps:
            1. Poll TCP connection from the under-test VM to the reference VM on NAD-VLAN-B
            2. Poll TCP connection from the under-test VM to the reference VM on NAD-VLAN-A

        Expected:
            - Under-test VM eventually has TCP connectivity to the reference VM on NAD-VLAN-B
            - Under-test VM has no TCP connectivity to the reference VM on NAD-VLAN-A
        """
        for ref_iface_name, nad, expect_connectivity, server_bind_dev in [
            (VM_IFACE_2, bridge_nad_b, True, GUEST_IFACE_2),
            (VM_IFACE_1, bridge_nad_a, False, GUEST_IFACE_1),
        ]:
            for ip in filter_link_local_addresses(
                ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=ref_iface_name).ipAddresses
            ):
                with subtests.test(msg=f"{ip} on {nad.name}"):
                    poll_tcp_connectivity(
                        client_vm=under_test_vm_two_ifaces,
                        server_vm=ref_vm,
                        server_ip=str(ip),
                        expect_connectivity=expect_connectivity,
                        client_bind_dev=GUEST_IFACE_1,
                        server_bind_dev=server_bind_dev,
                    )

    @pytest.mark.polarion("CNV-15946")
    def test_two_networks(
        self,
        subtests,
        under_test_vm_two_ifaces,
        bridge_nad_a,
        bridge_nad_b,
        ref_vm,
    ):
        """
        Test that both secondary Linux bridge networks on a running VM can have their VLANs
        changed in a single patch, with each network switching to a different VLAN.

        Preconditions:
            - Running under-test VM with two secondary Linux bridge networks:
              first network connected to NAD-VLAN-B, second network connected to NAD-VLAN-A
            - TCP connectivity established between the under-test VM first secondary network
              and the reference VM on NAD-VLAN-B
            - TCP connectivity established between the under-test VM second secondary network
              and the reference VM on NAD-VLAN-A

        Steps:
            1. Apply a single patch updating both secondary networks: first network to NAD-VLAN-A,
               second network to NAD-VLAN-B
            2. Wait for the change to be applied successfully (the update condition clears and
               the VM reaches synced status)

        Expected:
            - Under-test VM remains running after both NAD reference changes
            - Under-test VM first secondary network eventually has TCP connectivity to the reference VM on NAD-VLAN-A
            - Under-test VM second secondary network eventually has TCP connectivity to the reference VM on NAD-VLAN-B
        """
        update_nad_references(
            vm=under_test_vm_two_ifaces,
            updates={VM_IFACE_1: bridge_nad_a.name, VM_IFACE_2: bridge_nad_b.name},
        )
        under_test_vm_two_ifaces.wait_for_ready_status(status=True)

        for ref_iface_name, nad, client_bind_dev, server_bind_dev in [
            (VM_IFACE_2, bridge_nad_b, GUEST_IFACE_2, GUEST_IFACE_2),
            (VM_IFACE_1, bridge_nad_a, GUEST_IFACE_1, GUEST_IFACE_1),
        ]:
            for ip in filter_link_local_addresses(
                ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=ref_iface_name).ipAddresses
            ):
                with subtests.test(msg=f"{ip} on {nad.name}"):
                    poll_tcp_connectivity(
                        client_vm=under_test_vm_two_ifaces,
                        server_vm=ref_vm,
                        server_ip=str(ip),
                        client_bind_dev=client_bind_dev,
                        server_bind_dev=server_bind_dev,
                    )


@pytest.mark.jira("CNV-87878", run=False)
@pytest.mark.polarion("CNV-15947")
def test_non_migratable_vm_nad_change_not_applied(
    subtests,
    non_migratable_under_test_vm,
    bridge_nad_a,
    bridge_nad_b,
    ref_vm,
):
    """
    [NEGATIVE] Test that changing the NAD reference on a non-migratable VM does not
    silently succeed — the VM remains connected to the original network.

    Preconditions:
        - Non-migratable under-test VM backed by a ReadWriteOnce DataVolume (LiveMigratable: False)
          with a secondary Linux bridge network connected to NAD-VLAN-A
        - TCP connectivity established between the under-test VM and the reference VM on NAD-VLAN-A
        - No TCP connectivity between the under-test VM and the reference VM on NAD-VLAN-B

    Steps:
        1. Update the non-migratable under-test VM's secondary network to reference NAD-VLAN-B

    Expected:
        - Under-test VM remains running after the NAD reference change attempt
        - The VM reports a RestartRequired condition indicating the NAD reference change cannot be applied live
        - Non-migratable under-test VM retains connectivity to the reference VM on NAD-VLAN-A
        - Non-migratable under-test VM has no connectivity to the reference VM on NAD-VLAN-B
    """
    update_nad_references(vm=non_migratable_under_test_vm, updates={VM_IFACE_1: bridge_nad_b.name})
    non_migratable_under_test_vm.wait_for_condition(condition="RestartRequired", status="True")

    for ref_iface_name, nad, expect_connectivity, server_bind_dev in [
        (VM_IFACE_2, bridge_nad_b, False, GUEST_IFACE_2),
        (VM_IFACE_1, bridge_nad_a, True, GUEST_IFACE_1),
    ]:
        for ip in filter_link_local_addresses(
            ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=ref_iface_name).ipAddresses
        ):
            with subtests.test(msg=f"{ip} on {nad.name}"):
                poll_tcp_connectivity(
                    client_vm=non_migratable_under_test_vm,
                    server_vm=ref_vm,
                    server_ip=str(ip),
                    expect_connectivity=expect_connectivity,
                    server_bind_dev=server_bind_dev,
                )
