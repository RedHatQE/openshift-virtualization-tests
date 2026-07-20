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

__test__ = False


class TestVMTemplateAdmission:
    """
    Tests for VirtualMachineTemplate admission behavior under defaulted parameters.

    Preconditions:
        - OpenShift Virtualization cluster with common instance types deployed
    """

    @pytest.mark.polarion("CNV-16314")
    def test_valid_template_with_defaulted_parameters_accepted(self):
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

        Markers:
            - smoke
        """

    @pytest.mark.polarion("CNV-16315")
    def test_invalid_by_default_template_rejected(self):
        """
        [NEGATIVE] Test that a VirtualMachineTemplate whose default parameter values would
        always produce an invalid VM definition is rejected by the admission webhook.

        Steps:
            1. Submit a VirtualMachineTemplate resource whose defaulted parameters produce
               an invalid VM definition

        Expected:
            - VirtualMachineTemplate creation is rejected with an admission error indicating
              the template would always produce an invalid VM
        """
