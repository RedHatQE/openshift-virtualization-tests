"""
Live Update of NetworkAttachmentDefinition Reference

Tests the ability to dynamically change the NAD reference (networkName)
of secondary networks on running VMs through live migration, without requiring VM restarts.

STP Reference: TODO: Update after this merged
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/39

"""

__test__ = False

import pytest


class TestNADReferenceLiveUpdate:
    """
    Test live update of NAD reference on running VMs.

    Markers:
        - pytest.mark.ipv4
        - pytest.mark.ipv6

    Preconditions:
        - Multinode cluster with at least 2 schedulable worker nodes
        - NMState operator deployed
        - LiveUpdateNADRef feature gate enabled
        - VM rollout strategy set to LiveUpdate
        - Workload update method set to LiveMigrate
        - Two NetworkAttachmentDefinitions (NAD1, NAD2) with two different bridges
        - Running VM with secondary network attached to NAD1
        - Running VM with secondary network attached to NAD1
        - VMs are reachable from each other
        - VMs are live-migratable
    """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_nad_ref_change_sets_correct_conditions(self):
        """
        Test that RestartRequired condition is not set when only NAD reference changes.

        Preconditions:
            - Running VM with secondary network attached to NAD1

        Steps:
            1. Update VM spec to change multus.networkName of one secondary iface from NAD1 to NAD2
            2. Check VM/VMI conditions

        Expected:
            - RestartRequired condition is NOT present on the VM
            - VirtualMachineInstanceMigrationRequired condition appears on VMI
            - VirtualMachineInstanceMigrationRequired condition disappears from VMI
            - AgentConnected appears on the VMI
            - VMI becomes Ready
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_post_migration_isolation_from_previous_network(self):
        """
        Test that VM is isolated from the previous network after NAD reference change.

        Preconditions:
            - VM(1) is now connected to NAD2
            - VM(2) is still connected to NAD1

        Steps:
            1. Execute ping between the two VMs

        Expected:
            - Ping fails with 100% packet loss
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_guest_interface_mac_address_and_name_preserved(self):
        """
        Test that guest interface MAC address remains unchanged after NAD reference change.

        Preconditions:
            - Running VM(2) with secondary network attached to NAD1

        Steps:
            1. Record the MAC address and name of the secondary interface of the guest
            2. Update VM2 spec to change multus.networkName of this iface from NAD1 to NAD2
            3. Wait for VirtualMachineInstanceMigrationRequired condition to appear and disappear
            4. Wait for VMI to be ready
            5. Wait for AgentConnected condition on VMI.
            6. Read the MAC address and name of the secondary interface from VMI status

        Expected:
            - MAC address and nameremain unchanged
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_post_nad_change_connectivity_to_new_network(self):
        """
        Test that VM has network connectivity to the new network after NAD reference change.

        Preconditions:
            - Running VM(1) with secondary network attached to NAD1
            - Running VM(2) with secondary network attached to NAD1

        Steps:
            1. Execute ping from static VM2 to VM1

        Expected:
            - Ping succeeds
        """
