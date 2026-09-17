"""
VM Template Upgrade Continuity Tests

Tests that a VirtualMachineTemplate created directly, and a VirtualMachineTemplate
captured (via a VirtualMachineTemplateRequest) from a VM created by that template, both
survive a cluster upgrade, and that those pre-existing VirtualMachineTemplate remains usable
to create new VMs after the upgrade.

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-infra/virtual-machine-template.md

Markers:
    - upgrade
    - cnv_upgrade
    - ocp_upgrade
    - eus_upgrade
"""

import pytest

__test__ = False


class TestVMTemplateUpgrade:
    """
    Validate upgrade continuity for existing templates and vm template requests,
    including post-upgrade template usability.

    Pre-upgrade tests create a VirtualMachineTemplate directly and use it to create a VM,
    confirming the template's creation flow works. That VM is then captured by a
    VirtualMachineTemplateRequest into a new VirtualMachineTemplate, and deleted right
    after, since it is only used as the capture source and does not need to persist
    across the upgrade.
    Post-upgrade tests validate that both VirtualMachineTemplate resources and the
    VirtualMachineTemplateRequest persisted through the upgrade, and that the
    directly-created template can still be used to create a new VM.
    """

    """ Pre-upgrade tests """

    @pytest.mark.polarion("CNV-16822")
    def test_template_creation_before_upgrade(self):
        """
        Test that a VirtualMachineTemplate can be created before the cluster upgrade
        begins, and reaches a completed/Ready state.

        Preconditions:
            - Run before cluster upgrade.

        Steps:
            1. Create a VirtualMachineTemplate resource
            2. Wait for the VirtualMachineTemplate to become completed/Ready

        Expected:
            - VirtualMachineTemplate is created successfully and becomes completed/Ready
        """

    @pytest.mark.polarion("CNV-16821")
    def test_vm_creation_from_template_before_upgrade(self):
        """
        Test that a VM can be created from a VirtualMachineTemplate before the cluster
        upgrade begins. The VM is kept (not deleted), since it is reused as the source
        VM captured by a VirtualMachineTemplateRequest.

        Preconditions:
            - Run before cluster upgrade.
            - A VirtualMachineTemplate created before the upgrade

        Steps:
            1. Create a VM using the template

        Expected:
            - VM is created successfully from the template
        """

    @pytest.mark.polarion("CNV-16817")
    def test_template_request_before_upgrade(self):
        """
        Test that a VirtualMachineTemplateRequest can be created before the cluster
        upgrade begins, and that it captures an existing VM into a new
        VirtualMachineTemplate. The captured VM is deleted immediately after, since it is
        only used as the capture source and does not need to persist across the upgrade.

        Preconditions:
            - Run before cluster upgrade.
            - A VM created from the pre-existing VirtualMachineTemplate, to be captured
              into a new template

        Steps:
            1. Create a VirtualMachineTemplateRequest referencing the existing VM
            2. Wait for the request to become Ready
            3. Wait for the VirtualMachineTemplate referenced in the request's status to
               become completed/Ready
            4. Delete the VM

        Expected:
            - VirtualMachineTemplateRequest is created successfully and becomes Ready
            - A VirtualMachineTemplate is created from the request, referenced in its
              status, and becomes completed/Ready
        """

    """ Post-upgrade tests """

    @pytest.mark.polarion("CNV-16818")
    def test_template_resources_preserved_after_upgrade(self):
        """
        Test that a directly-created VirtualMachineTemplate, a VirtualMachineTemplateRequest,
        and the VirtualMachineTemplate it captured all remain present on the cluster, in
        their completed/Ready state, after the upgrade.

        Preconditions:
            - Run after cluster upgrade.
            - A VirtualMachineTemplate created directly before the upgrade, in a completed/Ready
              state
            - A VirtualMachineTemplateRequest created before the upgrade, in a completed/Ready
              state, and the VirtualMachineTemplate it captured, also in a completed/Ready state

        Steps:
            1. Get the directly-created VirtualMachineTemplate by name and check its state
            2. Get the VirtualMachineTemplateRequest by name and check its state
            3. Get the VirtualMachineTemplate referenced in the request's status and check
               its state

        Expected:
            - All three resources are still present after the upgrade
            - All three resources remain in the same completed/Ready state they were in
              before the upgrade
        """

    @pytest.mark.polarion("CNV-16819")
    def test_new_vm_creation_from_existing_template_succeeds_after_upgrade(self):
        """
        Test that a new VM can be created from each pre-existing VirtualMachineTemplate
        (the one created directly, and the one captured by the request) after the
        cluster upgrade.

        Preconditions:
            - Run after cluster upgrade.
            - A VirtualMachineTemplate created before the upgrade
            - A VirtualMachineTemplate captured from a VM by a VirtualMachineTemplateRequest,
              before the upgrade

        Steps:
            1. Create a new VM using the directly-created VirtualMachineTemplate
            2. Create a new VM using the captured VirtualMachineTemplate

        Expected:
            - A VM is created successfully from each pre-existing template
        """
