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

from tests.infrastructure.vm_template.utils import process_and_create_vm
from tests.upgrade_params import (
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
    VM_TEMPLATE_NODE_ID_PREFIX,
)
from utilities.constants.pytest import DEPENDENCY_SCOPE_SESSION
from utilities.constants.timeouts import TIMEOUT_1MIN

pytestmark = [
    pytest.mark.upgrade,
    pytest.mark.cnv_upgrade,
    pytest.mark.ocp_upgrade,
    pytest.mark.eus_upgrade,
]


class TestVMTemplatePreUpgrade:
    """
    Pre-upgrade tests: create a VirtualMachineTemplate directly and use it to create a VM,
    confirming the template's creation flow works. That VM is then captured by a
    VirtualMachineTemplateRequest into a new VirtualMachineTemplate. The source VM is
    removed once this class's tests finish, since it does not need to persist across
    the upgrade.

    Preconditions:
        - Run before cluster upgrade.
    """

    @pytest.mark.polarion("CNV-16822")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    # Post-upgrade tests depend on this to verify the template existed before the upgrade.
    @pytest.mark.dependency(name=f"{VM_TEMPLATE_NODE_ID_PREFIX}::test_template_created_before_upgrade")
    def test_template_creation_before_upgrade(self, vm_template_before_upgrade):
        """
        Test that a VirtualMachineTemplate can be created before the cluster upgrade
        begins, and reaches a completed/Ready state.

        Steps:
            1. Create a VirtualMachineTemplate resource
            2. Wait for the VirtualMachineTemplate to become completed/Ready

        Expected:
            - VirtualMachineTemplate is created successfully and becomes completed/Ready
        """
        vm_template_before_upgrade.wait_for_condition(
            condition=vm_template_before_upgrade.Condition.READY,
            status=vm_template_before_upgrade.Condition.Status.TRUE,
            timeout=TIMEOUT_1MIN,
        )

    @pytest.mark.polarion("CNV-16821")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    # test_template_request_before_upgrade depends on this to ensure the source VM exists.
    @pytest.mark.dependency(name=f"{VM_TEMPLATE_NODE_ID_PREFIX}::test_vm_creation_from_template_before_upgrade")
    def test_vm_creation_from_template_before_upgrade(
        self, vm_template_before_upgrade, vm_created_from_template_before_upgrade
    ):
        """
        Test that a VM can be created from a VirtualMachineTemplate before the cluster
        upgrade begins. The VM is kept alive until the end of this test class, since it
        is reused as the source VM captured by a VirtualMachineTemplateRequest.

        Preconditions:
            - A VirtualMachineTemplate created before the upgrade

        Steps:
            1. Create a VM using the template

        Expected:
            - VM is created successfully from the template
        """
        assert vm_created_from_template_before_upgrade.exists, (
            f"VM {vm_created_from_template_before_upgrade.name} should have been created "
            f"from template {vm_template_before_upgrade.name}"
        )

    @pytest.mark.polarion("CNV-16817")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.usefixtures("vm_template_request_before_upgrade")
    # Post-upgrade tests depend on this to verify the template request existed before the upgrade.
    @pytest.mark.dependency(
        name=f"{VM_TEMPLATE_NODE_ID_PREFIX}::test_template_request_before_upgrade",
        depends=[f"{VM_TEMPLATE_NODE_ID_PREFIX}::test_vm_creation_from_template_before_upgrade"],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_template_request_before_upgrade(self, captured_template):
        """
        Test that a VirtualMachineTemplateRequest can be created before the cluster
        upgrade begins, and that it captures an existing VM into a new
        VirtualMachineTemplate. The source VM is removed once this test class's tests
        finish.

        Preconditions:
            - A VM created from the pre-existing VirtualMachineTemplate, to be captured
              into a new template

        Steps:
            1. Create a VirtualMachineTemplateRequest referencing the existing VM
            2. Wait for the request to become Ready
            3. Wait for the VirtualMachineTemplate referenced in the request's status to
               become completed/Ready

        Expected:
            - VirtualMachineTemplateRequest is created successfully and becomes Ready
            - A VirtualMachineTemplate is created from the request, referenced in its
              status, and becomes completed/Ready
        """
        captured_template.wait_for_condition(
            condition=captured_template.Condition.READY,
            status=captured_template.Condition.Status.TRUE,
            timeout=TIMEOUT_1MIN,
        )


class TestVMTemplatePostUpgrade:
    """
    Post-upgrade tests: validate that both VirtualMachineTemplate resources and the
    VirtualMachineTemplateRequest persisted through the upgrade, and that the
    directly-created template can still be used to create a new VM.

    Preconditions:
        - Run after cluster upgrade.
    """

    @pytest.mark.polarion("CNV-16818")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    # Requires upgrade completion and pre-upgrade template and template request to have been created.
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{VM_TEMPLATE_NODE_ID_PREFIX}::test_template_created_before_upgrade",
            f"{VM_TEMPLATE_NODE_ID_PREFIX}::test_template_request_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_template_resources_preserved_after_upgrade(
        self, vm_template_before_upgrade, vm_template_request_before_upgrade, captured_template
    ):
        """
        Test that a directly-created VirtualMachineTemplate, a VirtualMachineTemplateRequest,
        and the VirtualMachineTemplate it captured all remain present on the cluster, in
        their completed/Ready state, after the upgrade.

        Preconditions:
            - A VirtualMachineTemplate created directly before the upgrade, in a completed/Ready
              state
            - A VirtualMachineTemplateRequest created before the upgrade, in a completed/Ready
              state, and the VirtualMachineTemplate it captured, also in a completed/Ready state

        Steps:
            1. For each of the three resources (directly-created VirtualMachineTemplate,
               VirtualMachineTemplateRequest, captured VirtualMachineTemplate):
               a. Verify the resource still exists on the cluster
               b. Wait for it to report Ready=True

        Expected:
            - All three resources are still present after the upgrade
            - All three resources report Ready=True after the upgrade
        """
        for resource in (vm_template_before_upgrade, vm_template_request_before_upgrade, captured_template):
            resource.wait_for_condition(
                condition=resource.Condition.READY,
                status=resource.Condition.Status.TRUE,
                timeout=TIMEOUT_1MIN,
            )

    @pytest.mark.polarion("CNV-16819")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    # Requires upgrade completion and pre-upgrade template to have been created.
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{VM_TEMPLATE_NODE_ID_PREFIX}::test_template_created_before_upgrade",
            f"{VM_TEMPLATE_NODE_ID_PREFIX}::test_template_request_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_new_vm_creation_from_existing_template_succeeds_after_upgrade(
        self, vm_template_before_upgrade, captured_template
    ):
        """
        Test that a new VM can be created from each pre-existing VirtualMachineTemplate
        (the one created directly, and the one captured by the request) after the
        cluster upgrade.

        Preconditions:
            - A VirtualMachineTemplate created before the upgrade
            - A VirtualMachineTemplate captured from a VM by a VirtualMachineTemplateRequest,
              before the upgrade

        Steps:
            1. Create a new VM using the directly-created VirtualMachineTemplate
            2. Create a new VM using the captured VirtualMachineTemplate

        Expected:
            - A VM is created successfully from each pre-existing template
        """
        for template in (vm_template_before_upgrade, captured_template):
            vm = process_and_create_vm(vmt=template)
            try:
                assert vm.exists, f"VM {vm.name} should have been created from template {template.name}"
            finally:
                vm.clean_up()
