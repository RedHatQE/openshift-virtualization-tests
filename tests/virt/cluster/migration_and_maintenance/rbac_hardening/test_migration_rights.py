import pytest
from kubernetes.dynamic.exceptions import ForbiddenError
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.role_binding import RoleBinding

from utilities.constants import UNPRIVILEGED_USER
from utilities.virt import VirtualMachineForTests, fedora_vm_body, migrate_vm_and_verify, running_vm

pytestmark = pytest.mark.rwx_default_storage


@pytest.fixture(scope="session")
def kubevirt_migrate_cluster_role(admin_client):
    return ClusterRole(name="kubevirt.io:migrate", client=admin_client, ensure_exists=True)


@pytest.fixture()
def unprivileged_user_migrate_rolebinding(admin_client, namespace, kubevirt_migrate_cluster_role):
    with RoleBinding(
        name="role-bind-kubevirt-migrate",
        namespace=namespace.name,
        client=admin_client,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_namespace=namespace.name,
        role_ref_kind=kubevirt_migrate_cluster_role.kind,
        role_ref_name=kubevirt_migrate_cluster_role.name,
    ) as role_binding:
        yield role_binding


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
