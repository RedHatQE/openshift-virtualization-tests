import pytest
from ocp_resources.datavolume import DataVolume

from tests.data_protection.oadp.utils import FILE_PATH_FOR_WINDOWS_BACKUP, wait_for_restored_dv
from utilities.constants import (
    FILE_NAME_FOR_BACKUP,
    TEXT_TO_TEST,
    TIMEOUT_10SEC,
    TIMEOUT_15MIN,
    Images,
)
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


class TestVeleroBackupHookOptOut:
    """
    Tests for Velero backup hook opt-out with paused VMs and full backup/restore.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/116

    Preconditions:
        - OADP operator installed and configured
        - Velero configured with default backup storage location
        - VM with opt-out annotation deployed and running
    """

    __test__ = False

    @pytest.mark.polarion("CNV-16267")
    def test_backup_paused_vm_hooks_disabled(self):
        """
        Test that Velero backup of a paused VM completes with hooks disabled.

        Preconditions:
            - VM deployed with kubevirt.io/skip-backup-hooks: "true"
            - VM paused via virtctl

        Steps:
            1. Run Velero backup targeting the VM namespace
            2. Wait for backup completion

        Expected:
            - Backup completes successfully without freeze/unfreeze hook execution
        """

    @pytest.mark.polarion("CNV-16268")
    def test_full_backup_restore_hooks_disabled(self):
        """
        Test that full Velero backup and restore completes with hooks disabled.

        Preconditions:
            - VM deployed with kubevirt.io/skip-backup-hooks: "true"
            - Test data written to VM disk

        Steps:
            1. Run Velero backup targeting the VM namespace
            2. Delete the VM and its namespace
            3. Restore from backup
            4. Wait for VM to reach Running state

        Expected:
            - VM is restored in Running state with test data intact
        """

    @pytest.mark.polarion("CNV-16269")
    def test_backup_paused_vm_default_hooks(self):
        """
        Test that Velero backup of a paused VM attempts hooks by default.

        Preconditions:
            - VM deployed without opt-out annotation
            - VM paused via virtctl

        Steps:
            1. Run Velero backup targeting the VM namespace
            2. Wait for backup completion

        Expected:
            - Backup completes with freeze/unfreeze hooks attempted
        """
