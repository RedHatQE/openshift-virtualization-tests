import pytest
from ocp_resources.datavolume import DataVolume

from tests.data_protection.oadp.utils import check_file_in_vm, wait_for_restored_dv
from utilities.constants import QUARANTINED, TIMEOUT_10SEC, Images

pytestmark = [
    pytest.mark.usefixtures("skip_if_no_storage_class_for_snapshot"),
    pytest.mark.xfail(
        reason=f"{QUARANTINED}: Restore bug ; RHCEPH-11933",
        run=False,
    ),
]


@pytest.mark.parametrize(
    "velero_backup_single_namespace",
    [
        pytest.param(
            {
                "wait_complete": False,
            },
            marks=pytest.mark.polarion("CNV-8580"),
        ),
    ],
    indirect=True,
)
def test_backup_while_dv_create(
    imported_dv_in_progress_second_namespace,
    velero_backup_single_namespace,
):
    velero_backup_single_namespace.wait_for_status(status="PartiallyFailed")


@pytest.mark.parametrize(
    "rhel_vm_with_data_volume_template",
    [
        pytest.param(
            {
                "dv_name": "dv-8695",
                "vm_name": "vm-8695",
                "volume_mode": DataVolume.VolumeMode.BLOCK,
                "rhel_image": Images.Rhel.RHEL9_3_IMG,
            },
            marks=pytest.mark.polarion("CNV-8695"),
        ),
    ],
    indirect=True,
)
def test_restore_multiple_namespaces(
    imported_dv_second_namespace,
    rhel_vm_with_data_volume_template,
    velero_restore_multiple_namespaces,
):
    imported_dv_second_namespace.wait_for_status(
        status=DataVolume.Status.SUCCEEDED,
        timeout=TIMEOUT_10SEC,
        stop_status=DataVolume.Status.IMPORT_IN_PROGRESS,
    )
    check_file_in_vm(vm=rhel_vm_with_data_volume_template)


@pytest.mark.parametrize(
    "rhel_vm_with_data_volume_template",
    [
        pytest.param(
            {
                "dv_name": "block-dv",
                "vm_name": "block-vm",
                "volume_mode": DataVolume.VolumeMode.BLOCK,
                "rhel_image": Images.Rhel.RHEL9_3_IMG,
            },
            marks=pytest.mark.polarion("CNV-10564"),
        ),
        pytest.param(
            {
                "dv_name": "filesystem-dv",
                "vm_name": "filesystem-vm",
                "volume_mode": DataVolume.VolumeMode.FILE,
                "rhel_image": Images.Rhel.RHEL9_3_IMG,
            },
            marks=pytest.mark.polarion("CNV-10565"),
        ),
    ],
    indirect=True,
)
def test_backup_vm_data_volume_template_with_datamover(
    rhel_vm_with_data_volume_template, velero_restore_first_namespace_with_datamover
):
    check_file_in_vm(vm=rhel_vm_with_data_volume_template)


@pytest.mark.polarion("CNV-10589")
def test_restore_vm_with_existing_dv(rhel_vm_from_existing_dv, velero_restore_second_namespace_with_datamover):
    check_file_in_vm(vm=rhel_vm_from_existing_dv)


@pytest.mark.polarion("CNV-10590")
def test_restore_cloned_dv(
    cloned_rhel_dv,
    velero_restore_second_namespace_with_datamover,
):
    wait_for_restored_dv(dv=cloned_rhel_dv)


@pytest.mark.polarion("CNV-10591")
def test_restore_uploaded_dv(
    uploaded_rhel_dv,
    velero_restore_second_namespace_with_datamover,
):
    wait_for_restored_dv(dv=uploaded_rhel_dv)
