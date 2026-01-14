import pytest

from tests.os_params import FEDORA_LATEST, FEDORA_LATEST_LABELS
from utilities.constants import StorageClassNames
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import migrate_vm_and_verify, vm_instance_from_template


@pytest.fixture
def vm_with_cephfs_storage(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_for_test_scope_function,
    cpu_for_migration,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_image_data_source_for_test_scope_function,
            storage_class=StorageClassNames.CEPHFS,
        ),
        vm_cpu_model=cpu_for_migration,
    ) as vm_from_template:
        yield vm_from_template


@pytest.fixture(scope="session")
def xfail_if_no_odf_cephfs_sc(cluster_storage_classes_names):
    """
    Skip test if no odf cephfs storage class available
    """
    if StorageClassNames.CEPHFS not in cluster_storage_classes_names:
        pytest.xfail(
            f"Cannot execute test, {StorageClassNames.CEPHFS} storage class is not deployed,"
            f"deployed storage classes: {cluster_storage_classes_names}"
        )


@pytest.mark.parametrize(
    ("golden_image_data_source_for_test_scope_function", "vm_with_cephfs_storage"),
    [
        pytest.param(
            {"os_dict": FEDORA_LATEST},
            {"vm_name": "cephfs-vm", "template_labels": FEDORA_LATEST_LABELS},
            marks=pytest.mark.polarion("CNV-11303"),
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("xfail_if_no_odf_cephfs_sc")
def test_vm_with_odf_cephfs_storage_class_migrates(vm_with_cephfs_storage):
    migrate_vm_and_verify(vm=vm_with_cephfs_storage)
