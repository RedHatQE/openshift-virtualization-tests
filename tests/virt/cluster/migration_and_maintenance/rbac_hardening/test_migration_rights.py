import pytest
from kubernetes.dynamic.exceptions import ForbiddenError

from utilities.virt import VirtualMachineForTests, fedora_vm_body, migrate_vm_and_verify, running_vm

pytestmark = pytest.mark.rwx_default_storage


@pytest.fixture(scope="module")
def unprivileged_user_vm(unprivileged_client, namespace):
    name = "namespace-admin-vm"
    with VirtualMachineForTests(
        name=name,
        client=unprivileged_client,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.polarion("CNV-11968")
def test_unprivileged_client_migrate_vm_negative(unprivileged_client, unprivileged_user_vm):
    """Test that namespace admin can't migrate a VM."""
    with pytest.raises(ForbiddenError):
        migrate_vm_and_verify(vm=unprivileged_user_vm, client=unprivileged_client, wait_for_migration_success=False)
        pytest.fail("Namespace admin shouldn't be able to migrate VM without kubevirt.io:migrate RoleBinding!")


@pytest.mark.polarion("CNV-11967")
@pytest.mark.usefixtures("unprivileged_user_migrate_rolebinding")
def test_unprivileged_client_migrate_vm(unprivileged_client, unprivileged_user_vm):
    """Test that namespace admin can migrate a VM when has kubevirt.io:migrate RoleBinding."""
    migrate_vm_and_verify(vm=unprivileged_user_vm, client=unprivileged_client)
