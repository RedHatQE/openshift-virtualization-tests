import pytest
from ocp_resources.virtual_machine_template import VirtualMachineTemplate
from ocp_resources.virtual_machine_template_request import VirtualMachineTemplateRequest

from tests.infrastructure.vm_template.constants import (
    VM_TEMPLATE_UPGRADE_PARAMETERS,
    VM_TEMPLATE_UPGRADE_REQUEST_NAME,
    VM_TEMPLATE_UPGRADE_TEMPLATE_NAME,
    VM_TEMPLATE_UPGRADE_VM_NAME,
)
from tests.infrastructure.vm_template.utils import process_and_create_vm, vm_template_upgrade_virtual_machine_spec
from utilities.constants.timeouts import TIMEOUT_1MIN


@pytest.fixture(scope="session")
def vm_template_before_upgrade(
    admin_client,
    upgrade_namespace_scope_session,
    storage_class_for_snapshot,
    rhel10_data_source_scope_session,
):
    """VirtualMachineTemplate created directly (not captured from an existing VM) before the upgrade.

    Its rendered VM's DataVolume uses a snapshot-capable storage class, since the VM created
    from this template (see ``vm_created_from_template_before_upgrade``) is also used as the
    capture source for the pre-upgrade VirtualMachineTemplateRequest.
    """
    with VirtualMachineTemplate(
        client=admin_client,
        name=VM_TEMPLATE_UPGRADE_TEMPLATE_NAME,
        namespace=upgrade_namespace_scope_session.name,
        parameters=VM_TEMPLATE_UPGRADE_PARAMETERS,
        virtual_machine=vm_template_upgrade_virtual_machine_spec(
            data_source=rhel10_data_source_scope_session,
            storage_class=storage_class_for_snapshot,
        ),
    ) as vm_template:
        yield vm_template


@pytest.fixture(scope="session")
def vm_template_request_before_upgrade(admin_client, upgrade_namespace_scope_session):
    """VirtualMachineTemplateRequest capturing the VM created from the pre-existing
    VirtualMachineTemplate into a new VirtualMachineTemplate, before the upgrade.
    """
    with VirtualMachineTemplateRequest(
        client=admin_client,
        name=VM_TEMPLATE_UPGRADE_REQUEST_NAME,
        namespace=upgrade_namespace_scope_session.name,
        virtual_machine_ref={
            "name": VM_TEMPLATE_UPGRADE_VM_NAME,
            "namespace": upgrade_namespace_scope_session.name,
        },
    ) as template_request:
        template_request.wait_for_condition(
            condition=template_request.Condition.READY,
            status=template_request.Condition.Status.TRUE,
            timeout=TIMEOUT_1MIN,
        )
        yield template_request


@pytest.fixture(scope="session")
def captured_template(vm_template_request_before_upgrade):
    """VirtualMachineTemplate captured by the pre-upgrade VirtualMachineTemplateRequest."""
    template_ref = vm_template_request_before_upgrade.instance.status.templateRef
    yield VirtualMachineTemplate(
        client=vm_template_request_before_upgrade.client,
        name=template_ref.name,
        namespace=vm_template_request_before_upgrade.namespace,
    )


@pytest.fixture(scope="class")
def vm_created_from_template_before_upgrade(vm_template_before_upgrade):
    """VM created by processing the pre-existing VirtualMachineTemplate.

    Used both to prove the template can create a VM, and as the capture source for the
    pre-upgrade VirtualMachineTemplateRequest. Deleted at the end of the pre-upgrade test
    class via fixture teardown, since it does not need to persist across the upgrade.
    """
    vm = process_and_create_vm(
        vmt=vm_template_before_upgrade,
        parameters={"NAME": VM_TEMPLATE_UPGRADE_VM_NAME},
    )
    yield vm
    vm.clean_up()
