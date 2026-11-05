import pytest
from ocp_resources.datavolume import DataVolume

from tests.data_protection.oadp.utils import (
    FILE_PATH_FOR_WINDOWS_BACKUP,
    golden_image_data_volume_from_virtual_machine_template,
    wait_for_restored_dv,
)
from utilities.constants import Images
from utilities.constants.oadp import FILE_NAME_FOR_BACKUP, RHEL_VIRTUAL_MACHINE_TEMPLATE_NAME, TEXT_TO_TEST
from utilities.constants.timeouts import TIMEOUT_1MIN, TIMEOUT_10SEC, TIMEOUT_15MIN
from utilities.oadp import check_file_in_running_vm
from utilities.storage import verify_file_in_windows_vm
from utilities.virt import wait_for_running_vm

pytestmark = pytest.mark.usefixtures("skip_if_no_storage_class_for_snapshot")


@pytest.mark.s390x
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


@pytest.mark.s390x
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
    check_file_in_running_vm(
        vm=rhel_vm_with_data_volume_template, file_name=FILE_NAME_FOR_BACKUP, file_content=TEXT_TO_TEST
    )


@pytest.mark.s390x
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
@pytest.mark.usefixtures("velero_restore_first_namespace_with_datamover")
def test_backup_vm_data_volume_template_with_datamover(rhel_vm_with_data_volume_template):
    check_file_in_running_vm(
        vm=rhel_vm_with_data_volume_template, file_name=FILE_NAME_FOR_BACKUP, file_content=TEXT_TO_TEST
    )


@pytest.mark.tier3
@pytest.mark.windows
@pytest.mark.polarion("CNV-8696")
@pytest.mark.usefixtures("velero_restore_first_namespace_without_datamover")
def test_backup_and_restore_windows_vm(windows_vm_with_data_volume_template):
    """
    Test Windows VM backup and restore without Data Mover using Velero snapshot.

    Preconditions:
        - Windows VM with a marker file containing test data
        - Velero backup created without Data Mover
        - Velero restore completed

    Steps:
        1. Wait for Windows VM to reach Running state
        2. Verify marker file exists at expected path
        3. Verify file content matches pre-backup text

    Expected:
        - Windows VM is Running
        - Marker file content equals TEXT_TO_TEST
    """
    wait_for_running_vm(
        vm=windows_vm_with_data_volume_template,
        wait_until_running_timeout=TIMEOUT_15MIN,
    )
    verify_file_in_windows_vm(
        windows_vm=windows_vm_with_data_volume_template,
        file_name_with_path=FILE_PATH_FOR_WINDOWS_BACKUP,
        file_content=TEXT_TO_TEST,
    )


@pytest.mark.s390x
@pytest.mark.polarion("CNV-10589")
@pytest.mark.usefixtures("velero_restore_second_namespace_with_datamover")
def test_restore_vm_with_existing_dv(rhel_vm_from_existing_dv):
    check_file_in_running_vm(vm=rhel_vm_from_existing_dv, file_name=FILE_NAME_FOR_BACKUP, file_content=TEXT_TO_TEST)


@pytest.mark.s390x
@pytest.mark.polarion("CNV-10590")
def test_restore_cloned_dv(
    cloned_rhel_dv,
    velero_restore_second_namespace_with_datamover,
):
    wait_for_restored_dv(dv=cloned_rhel_dv)


@pytest.mark.s390x
@pytest.mark.polarion("CNV-10591")
def test_restore_uploaded_dv(
    uploaded_rhel_dv,
    velero_restore_second_namespace_with_datamover,
):
    wait_for_restored_dv(dv=uploaded_rhel_dv)


@pytest.mark.usefixtures("velero_restore_rhel_virtual_machine_template")
def test_vm_backup_and_restore_rhel_vm_template(
    rhel_virtual_machine_template,
    rhel_virtual_machine_template_request,
    rhel_virtual_machine_instancetype,
    rhel_virtual_machine_preference,
):
    """Backup and restore a VirtualMachineTemplate captured from a running RHEL VM.

    Jira: https://issues.redhat.com/browse/CNV-94679

    Preconditions:
        - Running RHEL VM in the backup namespace with namespaced instance type and preference
        - VirtualMachineTemplateRequest that captured that VM into a VirtualMachineTemplate
        - Velero backup, namespace delete, and restore completed

    Steps:
        1. Wait for the restored VirtualMachineTemplate to become Ready
        2. Verify the restored template, preference, and instance type exist
        3. Verify the golden-image DataVolume referenced by the template is restored

    Expected:
        - Restored VirtualMachineTemplate is Ready
        - Restored preference and instance type exist
        - Golden-image DataVolume referenced by the template exists and succeeds
    """
    rhel_virtual_machine_template.wait_for_condition(
        condition=rhel_virtual_machine_template.Condition.READY,
        status=rhel_virtual_machine_template.Condition.Status.TRUE,
        timeout=TIMEOUT_1MIN,
    )
    assert rhel_virtual_machine_template.exists, (
        f"Expected restored template {RHEL_VIRTUAL_MACHINE_TEMPLATE_NAME} to exist"
    )
    assert rhel_virtual_machine_preference.exists, (
        f"Expected restored preference {rhel_virtual_machine_preference.name} to exist"
    )
    assert rhel_virtual_machine_instancetype.exists, (
        f"Expected restored instance type {rhel_virtual_machine_instancetype.name} to exist"
    )

    golden_image_data_volume = golden_image_data_volume_from_virtual_machine_template(
        virtual_machine_template=rhel_virtual_machine_template,
    )
    wait_for_restored_dv(dv=golden_image_data_volume)
    assert golden_image_data_volume.exists, (
        f"Expected restored golden-image DataVolume {golden_image_data_volume.name} to exist"
    )
