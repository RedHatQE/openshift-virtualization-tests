import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.resource import ResourceEditor

from utilities.constants import MIGRATION_POLICY_VM_LABEL
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
)


@pytest.fixture(scope="class")
def vm_for_multifd_test(
    namespace,
    unprivileged_client,
    cpu_for_migration,
):
    name = "vm-for-multifd-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        additional_labels=MIGRATION_POLICY_VM_LABEL,
        cpu_model=cpu_for_migration,
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def migration_policy_postcopy():
    with MigrationPolicy(
        name="multifd-postcopy-policy",
        allow_post_copy=True,
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as mp:
        yield mp


@pytest.fixture()
def migrated_vm_source_pod(vm_for_multifd_test):
    source_pod = vm_for_multifd_test.vmi.virt_launcher_pod
    migrate_vm_and_verify(vm=vm_for_multifd_test)
    return source_pod


@pytest.fixture()
def added_vm_cpu_limit(vm_for_multifd_test):
    # Add CPU limits to VM template spec
    ResourceEditor({
        vm_for_multifd_test: {"spec": {"template": {"spec": {"domain": {"resources": {"limits": {"cpu": "2"}}}}}}}
    }).update()

    # Restart VM so CPU limits take effect
    restart_vm_wait_for_running_vm(vm=vm_for_multifd_test)
