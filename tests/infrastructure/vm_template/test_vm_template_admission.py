"""
VM Template Admission Behavior Tests

Tests for VirtualMachineTemplate admission behavior: validate that templates whose
defaulted parameters always produce an invalid VM are rejected by the admission
webhook, and that templates who use the same fields as common instance types resolve
to a valid VM definition are accepted.

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-infra/virtual-machine-template.md

Markers:
    - tier2
"""

import pytest

from tests.infrastructure.vm_template.utils import process_and_create_vm


@pytest.mark.smoke
class TestVMTemplateAdmissionPositive:
    """
    Positive tests for VirtualMachineTemplate admission behavior under defaulted parameters.

    Preconditions:
        - OpenShift Virtualization cluster with enabled Template feature gate

    Markers:
        - smoke
    """

    @pytest.mark.polarion("CNV-16314")
    def test_valid_template_with_defaulted_parameters_accepted(self, valid_vm_template):
        """
        Test that a VirtualMachineTemplate whose default parameter values resolve to a
        valid VM definition is accepted by the cluster.

        The template uses default values that mirror the fields of a common instance type,
        ensuring the rendered VM definition is structurally valid.

        Steps:
            1. Submit a VirtualMachineTemplate whose parameters all have defaults modeled
               after a common instance type, producing a complete and valid VM definition

        Expected:
            - VirtualMachineTemplate is created successfully
        """
        assert valid_vm_template.exists, (
            f"VirtualMachineTemplate {valid_vm_template.name} should have been created successfully"
        )

    @pytest.mark.polarion("CNV-16336")
    def test_vm_created_from_valid_template(self, valid_vm_template):
        """
        Test that a VirtualMachine can be created using the spec defined in a valid
        VirtualMachineTemplate.

        Preconditions:
            - A valid VirtualMachineTemplate exists on the cluster

        Steps:
            1. Create a VirtualMachine using the instance type and preference parameters
               defined as defaults in the valid VirtualMachineTemplate

        Expected:
            - VirtualMachine is created successfully
        """
        process_and_create_vm(vmt=valid_vm_template)


@pytest.mark.polarion("CNV-16315")
def test_invalid_by_default_template_rejected():
    """
    [NEGATIVE] Test that a VirtualMachineTemplate whose default parameter values would
    always produce an invalid VM definition is rejected by the admission webhook.

    Preconditions:
        - OpenShift Virtualization cluster with enabled Template feature gate

    Steps:
        1. Submit a VirtualMachineTemplate resource whose defaulted parameters produce
           an invalid VM definition

    Expected:
        - VirtualMachineTemplate creation is rejected with an admission error indicating
          the template would always produce an invalid VM
    """


test_invalid_by_default_template_rejected.__test__ = False
