"""
VM Template Capability Disable and Reenable Tests

Tests for the Template capability feature gate: validate that disabling the capability
blocks new template workflows while preserving existing objects, and that re-enabling
the capability restores expected template workflows.

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-infra/virtual-machine-template.md

Markers:
    - tier2
    - post_upgrade
"""

import pytest

__test__ = False


@pytest.mark.incremental
class TestVMTemplateCapability:
    """
    Tests for VirtualMachineTemplate capability disable and reenable behavior.

    The tests run in order: the disable phase first, then the reenable phase.
    Each phase depends on the cluster state left by previous tests in the class.

    Preconditions:
        - OpenShift Virtualization cluster with the Template capability enabled
    """

    @pytest.mark.polarion("CNV-16316")
    def test_new_template_creation_blocked_after_capability_disabled(self):
        """
        [NEGATIVE] Test that creating a new VirtualMachineTemplate is blocked after the
        Template capability is disabled.

        Preconditions:
            - OpenShift Virtualization cluster with the Template capability enabled

        Steps:
            1. Disable the Template capability on the cluster
            2. Attempt to create a new VirtualMachineTemplate resource

        Expected:
            - VirtualMachineTemplate creation is rejected
        """

    @pytest.mark.polarion("CNV-16317")
    def test_new_template_request_blocked_after_capability_disabled(self):
        """
        [NEGATIVE] Test that creating a new VirtualMachineTemplateRequest is blocked
        while the Template capability is disabled.

        Preconditions:
            - Template capability is disabled on the cluster

        Steps:
            1. Attempt to create a new VirtualMachineTemplateRequest resource

        Expected:
            - VirtualMachineTemplateRequest creation is rejected
        """

    @pytest.mark.polarion("CNV-16318")
    def test_existing_templates_preserved_after_capability_disabled(self):
        """
        Test that existing VirtualMachineTemplate resources remain present on the cluster
        after the Template capability is disabled.

        Preconditions:
            - Template capability is disabled on the cluster
            - A VirtualMachineTemplate existed on the cluster before the capability was disabled

        Steps:
            1. List VirtualMachineTemplate resources on the cluster

        Expected:
            - The pre-existing VirtualMachineTemplate is still present
        """

    @pytest.mark.polarion("CNV-16319")
    def test_existing_template_requests_preserved_after_capability_disabled(self):
        """
        Test that existing VirtualMachineTemplateRequest resources remain present on the
        cluster after the Template capability is disabled.

        Preconditions:
            - Template capability is disabled on the cluster
            - A VirtualMachineTemplateRequest existed on the cluster before the capability
              was disabled

        Steps:
            1. List VirtualMachineTemplateRequest resources on the cluster

        Expected:
            - The pre-existing VirtualMachineTemplateRequest is still present
        """

    @pytest.mark.polarion("CNV-16320")
    def test_new_template_creation_succeeds_after_capability_reenabled(self):
        """
        Test that creating a new VirtualMachineTemplate succeeds after the Template
        capability is re-enabled following a disable.

        Preconditions:
            - Template capability was previously disabled and is now re-enabled

        Steps:
            1. Create a new VirtualMachineTemplate resource

        Expected:
            - VirtualMachineTemplate is created successfully
        """

    @pytest.mark.polarion("CNV-16321")
    def test_vm_creation_from_template_succeeds_after_capability_reenabled(self):
        """
        Test that creating a VM from a template succeeds after the Template capability
        is re-enabled following a disable.

        Preconditions:
            - Template capability is re-enabled on the cluster
            - A VirtualMachineTemplate exists on the cluster

        Steps:
            1. Create a VirtualMachineTemplateRequest referencing the existing template

        Expected:
            - VirtualMachineTemplateRequest is accepted and a new VM is created from the
              template
        """
