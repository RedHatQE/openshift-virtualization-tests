import pytest

from tests.os_params import FEDORA_LATEST, FEDORA_LATEST_LABELS
from utilities.constants import StorageClassNames
from utilities.virt import migrate_vm_and_verify, vm_instance_from_template


@pytest.fixture()
def vm_with_common_cpu_model_scope_function(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_test_scope_function,
    cpu_for_migration,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_test_scope_function,
        vm_cpu_model=cpu_for_migration,
    ) as vm_from_template:
        yield vm_from_template


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_function,"
    "golden_image_data_volume_template_for_test_scope_function,"
    "vm_with_common_cpu_model_scope_function",
    [
        pytest.param(
            {"os_dict": FEDORA_LATEST},
            {"storage_class": StorageClassNames.CEPHFS},
            {"vm_name": "cephfs-vm", "template_labels": FEDORA_LATEST_LABELS},
            marks=pytest.mark.polarion("CNV-11303"),
        )
    ],
    indirect=True,
)
def test_vm_with_odf_cephfs_storage_class_migrates(
    skip_test_if_no_odf_cephfs_sc, vm_with_common_cpu_model_scope_function
):
    migrate_vm_and_verify(vm=vm_with_common_cpu_model_scope_function)
