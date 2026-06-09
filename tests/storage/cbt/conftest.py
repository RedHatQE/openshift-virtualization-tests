"""
CBT (Changed Block Tracking) test fixtures.

Fixtures for setting up VMs, backups, and restores for CBT testing.
"""

import secrets
import shlex
from contextlib import ExitStack

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.secret import Secret
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_backup import VirtualMachineBackup
from ocp_resources.virtual_machine_backup_tracker import VirtualMachineBackupTracker
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pyhelper_utils.shell import run_ssh_commands

from tests.storage.cbt.utils import (
    CBT_BOOT_DISK_TEST_DATA_FILE,
    CBT_DATA_DISK_DEVICE,
    CBT_DATA_DISK_MOUNT_PATH,
    CBT_DATA_DISK_TEST_DATA,
    CBT_DATA_DISK_TEST_DATA_FILE,
    CBT_ENABLED_LABEL,
    CBT_HOTPLUG_DISK_DEVICE,
    CBT_HOTPLUG_DISK_MOUNT_PATH,
    CBT_HOTPLUG_DISK_TEST_DATA,
    CBT_HOTPLUG_DISK_TEST_DATA_FILE,
    CBT_INCREMENTAL_TEST_DATA,
    CBT_INCREMENTAL_TEST_DATA_FILE,
    CBT_MULTI_INCREMENTAL_DATA_PHASE_1,
    CBT_MULTI_INCREMENTAL_DATA_PHASE_2,
    CBT_MULTI_INCREMENTAL_TEST_DATA_FILE_PHASE_1,
    CBT_MULTI_INCREMENTAL_TEST_DATA_FILE_PHASE_2,
    CBT_POST_MIGRATION_TEST_DATA,
    CBT_POST_MIGRATION_TEST_DATA_FILE,
    CBT_TEST_DATA,
    CBT_WINDOWS_INCREMENTAL_TEST_DATA,
    CBT_WINDOWS_INCREMENTAL_TEST_DATA_FILE,
    CBT_WINDOWS_TEST_DATA,
    CBT_WINDOWS_TEST_DATA_FILE,
    CBT_WINDOWS_TEST_USER_DIR,
    CONCURRENT_CBT_VM_COUNT,
    DATA_DISK_SIZE,
    UNDERSIZED_BACKUP_PVC_SIZE,
    backup_tracker_source_dict,
    chown_mount_path_for_vm_user,
    get_vm_disk_volume_names,
    mount_cbt_data_disk_on_vm,
    mount_cbt_hotplug_disk_on_vm,
    read_file_content_from_vm,
    release_pull_mode_backup,
    restore_vm_from_backup,
    wait_for_backup_to_fail,
)
from tests.utils import create_windows2022_dv_from_registry
from utilities.constants import (
    DV_DISK,
    OS_FLAVOR_RHEL,
    OS_FLAVOR_WIN_CONTAINER_DISK,
    RHEL9_PREFERENCE,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    U1_LARGE,
    U1_SMALL,
    WINDOWS_2K22_PREFERENCE,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import (
    add_dv_to_vm,
    create_dv,
    data_volume_template_with_source_ref_dict,
    verify_file_in_windows_vm,
    virtctl_volume,
    wait_for_vm_volume_ready,
    write_file_via_ssh,
    write_file_windows_vm,
)
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify, running_vm, wait_for_windows_vm


@pytest.fixture(scope="module")
def incremental_backup_feature_gate_enabled(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_module,
):
    """
    Enable incrementalBackup feature gate in HyperConverged CR.

    Yields while the feature gate remains enabled.
    """
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: {"spec": {"featureGates": {"incrementalBackup": True}}},
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=admin_client,
        hco_namespace=hco_namespace.name,
    ):
        yield


@pytest.fixture(scope="module")
def cbt_label_selectors_configured(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_module,
    incremental_backup_feature_gate_enabled,
):
    """
    Configure CBT label selectors in HyperConverged CR.

    Yields while the label selectors remain configured.
    """
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: {
                "spec": {
                    "changedBlockTrackingLabelSelectors": {
                        "virtualMachineLabelSelector": {"matchLabels": CBT_ENABLED_LABEL},
                    },
                },
            },
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=admin_client,
        hco_namespace=hco_namespace.name,
    ):
        yield


@pytest.fixture()
def vm_with_cbt_label(
    request,
    unprivileged_client,
    namespace,
    cbt_label_selectors_configured,
    storage_class_name_scope_module,
    rhel9_data_source_scope_session,
):
    """
    VM with CBT enabled, started, and test data written.

    Returns:
        VirtualMachine: Running VM with CBT enabled and test data written
    """
    vm_name = getattr(request, "param", {}).get("name", "cbt-vm")

    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(client=unprivileged_client, name=RHEL9_PREFERENCE),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel9_data_source_scope_session,
            storage_class=storage_class_name_scope_module,
        ),
        os_flavor=OS_FLAVOR_RHEL,
        label=CBT_ENABLED_LABEL,
    ) as vm:
        running_vm(vm=vm)
        write_file_via_ssh(vm=vm, filename=CBT_BOOT_DISK_TEST_DATA_FILE, content=CBT_TEST_DATA)
        yield vm


@pytest.fixture()
def backup_tracker_for_vm(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
):
    """
    VirtualMachineBackupTracker for the VM.

    Returns:
        VirtualMachineBackupTracker: Backup tracker for the VM
    """
    with VirtualMachineBackupTracker(
        name=f"{vm_with_cbt_label.name}-tracker",
        namespace=namespace.name,
        client=unprivileged_client,
        source={
            "apiGroup": VirtualMachine.api_group,
            "kind": "VirtualMachine",
            "name": vm_with_cbt_label.name,
        },
    ) as tracker:
        yield tracker


@pytest.fixture()
def backup_pvc(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    storage_class_name_scope_module,
):
    """
    PVC for storing backup output (push mode).

    Returns:
        PersistentVolumeClaim: PVC for backup storage
    """
    source_disk_size = vm_with_cbt_label.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"]
    backup_pvc_size = f"{parse_quantity(source_disk_size) // (1024**3) + 10}Gi"

    with PersistentVolumeClaim(
        name="cbt-backup-pvc",
        namespace=namespace.name,
        client=unprivileged_client,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=backup_pvc_size,
        storage_class=storage_class_name_scope_module,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as pvc:
        yield pvc


@pytest.fixture()
def completed_full_backup_push_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_vm,
    backup_pvc,
):
    """
    Full backup in push mode, completed.

    Returns:
        VirtualMachineBackup: Completed backup
    """
    with VirtualMachineBackup(
        name="full-backup-push",
        namespace=namespace.name,
        client=unprivileged_client,
        mode=VirtualMachineBackup.Mode.PUSH,
        pvc_name=backup_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.DONE,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_full_backup_push_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_full_backup_push_mode,
    vm_with_cbt_label,
    backup_pvc,
    storage_class_name_scope_module,
):
    """
    VM restored from full backup and started.

    Returns:
        VirtualMachine: Running restored VM
    """
    # Delete the original VM to simulate restore scenario
    vm_with_cbt_label.delete(wait=True)

    source_disk_size = vm_with_cbt_label.data_volume_template["spec"]["storage"]["resources"]["requests"][
        "storage"
    ]

    restored_vm = restore_vm_from_backup(
        backup=completed_full_backup_push_mode,
        restored_vm_name=f"{vm_with_cbt_label.name}-restored",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        admin_client=admin_client,
        backup_pvc_name=backup_pvc.name,
    )

    # Start the restored VM
    running_vm(vm=restored_vm)

    yield restored_vm

    # Cleanup
    restored_vm.delete(wait=True)


@pytest.fixture()
def test_data_from_restored_vm_push_mode(restored_vm_from_full_backup_push_mode):
    """
    Read test data from restored VM.

    Returns:
        str: Content of the test data file from restored VM
    """
    return read_file_content_from_vm(
        vm=restored_vm_from_full_backup_push_mode,
        file_path=CBT_BOOT_DISK_TEST_DATA_FILE,
    )


# Pull mode fixtures


@pytest.fixture()
def scratch_pvc(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
):
    """
    Scratch PVC for pull mode backup operations.

    Returns:
        PersistentVolumeClaim: Scratch PVC
    """
    with PersistentVolumeClaim(
        name="cbt-scratch-pvc",
        namespace=namespace.name,
        client=unprivileged_client,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size="40Gi",  # Must be larger than source disk (30Gi) to accommodate backup data
        storage_class=storage_class_name_scope_module,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as pvc:
        yield pvc


@pytest.fixture()
def pull_mode_token_secret_name() -> str:
    """
    Secret name for pull-mode export authentication.

    Returns:
        str: Name referenced by VirtualMachineBackup spec.tokenSecretRef
    """
    return "cbt-pull-token-secret"


@pytest.fixture()
def pull_mode_token_secret(
    unprivileged_client,
    namespace,
    pull_mode_token_secret_name,
):
    """
    User-provided export token secret for pull-mode backup authentication.

    Pull-mode backups require a user-generated token in tokenSecretRef; the export
    endpoints authorize external clients using this secret value.

    Yields:
        Secret: Pull-mode token secret
    """
    export_token = secrets.token_urlsafe(nbytes=16)
    with Secret(
        name=pull_mode_token_secret_name,
        namespace=namespace.name,
        client=unprivileged_client,
        string_data={"token": export_token},
    ) as secret:
        yield secret


@pytest.fixture()
def completed_full_backup_pull_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_vm,
    scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
):
    """
    Full backup in pull mode, completed.

    Returns:
        VirtualMachineBackup: Completed backup with export endpoint ready
    """
    with VirtualMachineBackup(
        name="full-backup-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        mode=VirtualMachineBackup.Mode.PULL,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=scratch_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.EXPORT_READY,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_full_backup_pull_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_full_backup_pull_mode,
    vm_with_cbt_label,
    storage_class_name_scope_module,
):
    """
    VM restored from full backup (pull mode) and started.

    Returns:
        VirtualMachine: Running restored VM
    """
    source_disk_size = vm_with_cbt_label.data_volume_template["spec"]["storage"]["resources"]["requests"][
        "storage"
    ]

    restored_vm = restore_vm_from_backup(
        backup=completed_full_backup_pull_mode,
        restored_vm_name=f"{vm_with_cbt_label.name}-restored-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        admin_client=admin_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
    )

    vm_with_cbt_label.delete(wait=True)

    running_vm(vm=restored_vm)

    yield restored_vm

    # Cleanup
    restored_vm.delete(wait=True)


@pytest.fixture()
def test_data_from_restored_vm_pull_mode(restored_vm_from_full_backup_pull_mode):
    """
    Read test data from restored VM (pull mode).

    Returns:
        str: Content of the test data file from restored VM
    """
    return read_file_content_from_vm(
        vm=restored_vm_from_full_backup_pull_mode,
        file_path=CBT_BOOT_DISK_TEST_DATA_FILE,
    )


# Incremental backup fixtures (push mode)


@pytest.fixture()
def incremental_test_data_written_to_vm(
    vm_with_cbt_label,
    completed_full_backup_push_mode,
):
    """
    Incremental test data written to VM after full backup (push mode).

    Returns:
        VirtualMachine: VM with incremental test data written
    """
    write_file_via_ssh(
        vm=vm_with_cbt_label,
        filename=CBT_INCREMENTAL_TEST_DATA_FILE,
        content=CBT_INCREMENTAL_TEST_DATA,
    )
    yield vm_with_cbt_label


@pytest.fixture()
def completed_incremental_backup_push_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_vm,
    backup_pvc,
    incremental_test_data_written_to_vm,
):
    """
    Incremental backup in push mode, completed.

    Returns:
        VirtualMachineBackup: Completed incremental backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name="incremental-backup-push",
        namespace=namespace.name,
        client=unprivileged_client,
        pvc_name=backup_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.DONE,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_incremental_backup_push_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_incremental_backup_push_mode,
    vm_with_cbt_label,
    backup_pvc,
    storage_class_name_scope_module,
):
    """
    VM restored from incremental backup (push mode) and started.

    Returns:
        VirtualMachine: Running restored VM
    """
    vm_with_cbt_label.delete(wait=True)

    source_disk_size = vm_with_cbt_label.data_volume_template["spec"]["storage"]["resources"]["requests"][
        "storage"
    ]

    restored_vm = restore_vm_from_backup(
        backup=completed_incremental_backup_push_mode,
        restored_vm_name=f"{vm_with_cbt_label.name}-restored-incremental",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        admin_client=admin_client,
        backup_pvc_name=backup_pvc.name,
    )

    running_vm(vm=restored_vm)

    yield restored_vm

    restored_vm.delete(wait=True)


# Incremental backup fixtures (pull mode)


@pytest.fixture()
def incremental_test_data_written_to_vm_pull_mode(
    vm_with_cbt_label,
    completed_full_backup_pull_mode,
):
    """
    Incremental test data written to VM after full backup (pull mode).

    Returns:
        VirtualMachine: VM with incremental test data written
    """
    write_file_via_ssh(
        vm=vm_with_cbt_label,
        filename=CBT_INCREMENTAL_TEST_DATA_FILE,
        content=CBT_INCREMENTAL_TEST_DATA,
    )
    release_pull_mode_backup(backup=completed_full_backup_pull_mode)
    yield vm_with_cbt_label


@pytest.fixture()
def completed_incremental_backup_pull_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_vm,
    scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
    incremental_test_data_written_to_vm_pull_mode,
):
    """
    Incremental backup in pull mode, completed.

    Returns:
        VirtualMachineBackup: Completed incremental backup with export endpoint ready
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name="incremental-backup-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=scratch_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.EXPORT_READY,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_incremental_backup_pull_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_incremental_backup_pull_mode,
    vm_with_cbt_label,
    storage_class_name_scope_module,
):
    """
    VM restored from incremental backup (pull mode) and started.

    Returns:
        VirtualMachine: Running restored VM
    """
    source_disk_size = vm_with_cbt_label.data_volume_template["spec"]["storage"]["resources"]["requests"][
        "storage"
    ]

    restored_vm = restore_vm_from_backup(
        backup=completed_incremental_backup_pull_mode,
        restored_vm_name=f"{vm_with_cbt_label.name}-restored-incremental-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        admin_client=admin_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
    )

    vm_with_cbt_label.delete(wait=True)

    running_vm(vm=restored_vm)

    yield restored_vm

    restored_vm.delete(wait=True)


# Multiple incremental backup fixtures (push mode)


@pytest.fixture()
def multi_incremental_phase_1_data_written(
    vm_with_cbt_label,
    completed_full_backup_push_mode,
):
    """
    Phase 1 multi-incremental test data written after full backup (push mode).

    Returns:
        VirtualMachine: VM with phase 1 test data written
    """
    write_file_via_ssh(
        vm=vm_with_cbt_label,
        filename=CBT_MULTI_INCREMENTAL_TEST_DATA_FILE_PHASE_1,
        content=CBT_MULTI_INCREMENTAL_DATA_PHASE_1,
    )
    yield vm_with_cbt_label


@pytest.fixture()
def completed_first_incremental_backup_push_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_vm,
    backup_pvc,
    multi_incremental_phase_1_data_written,
):
    """
    First incremental backup in push mode, completed.

    Returns:
        VirtualMachineBackup: Completed first incremental backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name="first-incremental-backup-push",
        namespace=namespace.name,
        client=unprivileged_client,
        pvc_name=backup_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.DONE,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def multi_incremental_phase_2_data_written(
    vm_with_cbt_label,
    completed_first_incremental_backup_push_mode,
):
    """
    Phase 2 multi-incremental test data written after first incremental backup (push mode).

    Returns:
        VirtualMachine: VM with phase 2 test data written
    """
    write_file_via_ssh(
        vm=vm_with_cbt_label,
        filename=CBT_MULTI_INCREMENTAL_TEST_DATA_FILE_PHASE_2,
        content=CBT_MULTI_INCREMENTAL_DATA_PHASE_2,
    )
    yield vm_with_cbt_label


@pytest.fixture()
def completed_second_incremental_backup_push_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_vm,
    backup_pvc,
    multi_incremental_phase_2_data_written,
):
    """
    Second incremental backup in push mode, completed.

    Returns:
        VirtualMachineBackup: Completed second incremental backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name="second-incremental-backup-push",
        namespace=namespace.name,
        client=unprivileged_client,
        pvc_name=backup_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.DONE,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_second_incremental_backup_push_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_second_incremental_backup_push_mode,
    vm_with_cbt_label,
    backup_pvc,
    storage_class_name_scope_module,
):
    """
    VM restored from second incremental backup (push mode) and started.

    Returns:
        VirtualMachine: Running restored VM
    """
    vm_with_cbt_label.delete(wait=True)

    source_disk_size = vm_with_cbt_label.data_volume_template["spec"]["storage"]["resources"]["requests"][
        "storage"
    ]

    restored_vm = restore_vm_from_backup(
        backup=completed_second_incremental_backup_push_mode,
        restored_vm_name=f"{vm_with_cbt_label.name}-restored-multi-incremental",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        admin_client=admin_client,
        backup_pvc_name=backup_pvc.name,
    )

    running_vm(vm=restored_vm)

    yield restored_vm

    restored_vm.delete(wait=True)


# Multiple incremental backup fixtures (pull mode)


@pytest.fixture()
def multi_incremental_phase_1_data_written_pull_mode(
    vm_with_cbt_label,
    completed_full_backup_pull_mode,
):
    """
    Phase 1 multi-incremental test data written after full backup (pull mode).

    Returns:
        VirtualMachine: VM with phase 1 test data written
    """
    write_file_via_ssh(
        vm=vm_with_cbt_label,
        filename=CBT_MULTI_INCREMENTAL_TEST_DATA_FILE_PHASE_1,
        content=CBT_MULTI_INCREMENTAL_DATA_PHASE_1,
    )
    release_pull_mode_backup(backup=completed_full_backup_pull_mode)
    yield vm_with_cbt_label


@pytest.fixture()
def completed_first_incremental_backup_pull_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_vm,
    scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
    multi_incremental_phase_1_data_written_pull_mode,
):
    """
    First incremental backup in pull mode, completed.

    Returns:
        VirtualMachineBackup: Completed first incremental backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name="first-incremental-backup-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=scratch_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.EXPORT_READY,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def multi_incremental_phase_2_data_written_pull_mode(
    vm_with_cbt_label,
    completed_first_incremental_backup_pull_mode,
):
    """
    Phase 2 multi-incremental test data written after first incremental backup (pull mode).

    Returns:
        VirtualMachine: VM with phase 2 test data written
    """
    write_file_via_ssh(
        vm=vm_with_cbt_label,
        filename=CBT_MULTI_INCREMENTAL_TEST_DATA_FILE_PHASE_2,
        content=CBT_MULTI_INCREMENTAL_DATA_PHASE_2,
    )
    release_pull_mode_backup(backup=completed_first_incremental_backup_pull_mode)
    yield vm_with_cbt_label


@pytest.fixture()
def completed_second_incremental_backup_pull_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_vm,
    scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
    multi_incremental_phase_2_data_written_pull_mode,
):
    """
    Second incremental backup in pull mode, completed.

    Returns:
        VirtualMachineBackup: Completed second incremental backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name="second-incremental-backup-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=scratch_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.EXPORT_READY,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_second_incremental_backup_pull_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_second_incremental_backup_pull_mode,
    vm_with_cbt_label,
    storage_class_name_scope_module,
):
    """
    VM restored from second incremental backup (pull mode) and started.

    Returns:
        VirtualMachine: Running restored VM
    """
    source_disk_size = vm_with_cbt_label.data_volume_template["spec"]["storage"]["resources"]["requests"][
        "storage"
    ]

    restored_vm = restore_vm_from_backup(
        backup=completed_second_incremental_backup_pull_mode,
        restored_vm_name=f"{vm_with_cbt_label.name}-restored-multi-incremental-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        admin_client=admin_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
    )

    vm_with_cbt_label.delete(wait=True)

    running_vm(vm=restored_vm)

    yield restored_vm

    restored_vm.delete(wait=True)


# Multiple disk backup fixtures


@pytest.fixture()
def data_disk_dv_for_cbt_vm(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
):
    """
    Blank data disk DataVolume for CBT multi-disk testing.

    Returns:
        DataVolume: Blank 5Gi DataVolume
    """
    with create_dv(
        source="blank",
        dv_name="cbt-data-disk-dv",
        client=unprivileged_client,
        namespace=namespace.name,
        size=DATA_DISK_SIZE,
        storage_class=storage_class_name_scope_module,
    ) as data_volume:
        yield data_volume


@pytest.fixture()
def vm_with_boot_and_data_disk(
    vm_with_cbt_label,
    data_disk_dv_for_cbt_vm,
):
    """
    VM with boot and data disks, data disk formatted, mounted, and test data written.

    Returns:
        VirtualMachine: Running VM with test data on both disks
    """
    vm_with_cbt_label.stop(wait=True)
    add_dv_to_vm(vm=vm_with_cbt_label, dv_name=data_disk_dv_for_cbt_vm.name)
    running_vm(vm=vm_with_cbt_label)
    run_ssh_commands(
        host=vm_with_cbt_label.ssh_exec,
        commands=[
            shlex.split(f"sudo mkdir -p {CBT_DATA_DISK_MOUNT_PATH}"),
            shlex.split(f"sudo mkfs.ext4 {CBT_DATA_DISK_DEVICE}"),
            shlex.split(f"sudo mount {CBT_DATA_DISK_DEVICE} {CBT_DATA_DISK_MOUNT_PATH}"),
        ],
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )
    chown_mount_path_for_vm_user(vm=vm_with_cbt_label, mount_path=CBT_DATA_DISK_MOUNT_PATH)
    write_file_via_ssh(
        vm=vm_with_cbt_label,
        filename=CBT_DATA_DISK_TEST_DATA_FILE,
        content=CBT_DATA_DISK_TEST_DATA,
    )
    yield vm_with_cbt_label


@pytest.fixture()
def backup_tracker_for_multi_disk_vm(
    unprivileged_client,
    namespace,
    vm_with_boot_and_data_disk,
):
    """
    VirtualMachineBackupTracker for the multi-disk VM.

    Returns:
        VirtualMachineBackupTracker: Backup tracker for the multi-disk VM
    """
    with VirtualMachineBackupTracker(
        name=f"{vm_with_boot_and_data_disk.name}-tracker",
        namespace=namespace.name,
        client=unprivileged_client,
        source={
            "apiGroup": "kubevirt.io",
            "kind": "VirtualMachine",
            "name": vm_with_boot_and_data_disk.name,
        },
    ) as tracker:
        yield tracker


@pytest.fixture()
def completed_full_backup_multi_disk_push_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_multi_disk_vm,
    backup_pvc,
):
    """
    Full backup of multi-disk VM in push mode, completed.

    Returns:
        VirtualMachineBackup: Completed full backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name="full-backup-multi-disk-push",
        namespace=namespace.name,
        client=unprivileged_client,
        pvc_name=backup_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_multi_disk_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.DONE,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_multi_disk_backup_push_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_full_backup_multi_disk_push_mode,
    vm_with_boot_and_data_disk,
    data_disk_dv_for_cbt_vm,
    backup_pvc,
    storage_class_name_scope_module,
):
    """
    Multi-disk VM restored from full backup (push mode) and started.

    Returns:
        VirtualMachine: Running restored VM with boot and data disks
    """
    vm_with_boot_and_data_disk.delete(wait=True)

    source_disk_size = vm_with_boot_and_data_disk.data_volume_template["spec"]["storage"]["resources"]["requests"][
        "storage"
    ]
    source_volume_names = [DV_DISK, data_disk_dv_for_cbt_vm.name]

    restored_vm = restore_vm_from_backup(
        backup=completed_full_backup_multi_disk_push_mode,
        restored_vm_name=f"{vm_with_boot_and_data_disk.name}-restored-multi-disk",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        admin_client=admin_client,
        backup_pvc_name=backup_pvc.name,
        data_disk_size=DATA_DISK_SIZE,
        source_volume_names=source_volume_names,
    )

    running_vm(vm=restored_vm)
    mount_cbt_data_disk_on_vm(vm=restored_vm)

    yield restored_vm

    restored_vm.delete(wait=True)


@pytest.fixture()
def completed_full_backup_multi_disk_pull_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_multi_disk_vm,
    scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
):
    """
    Full backup of multi-disk VM in pull mode, completed.

    Returns:
        VirtualMachineBackup: Completed full backup with export endpoint ready
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name="full-backup-multi-disk-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=scratch_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_multi_disk_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.EXPORT_READY,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_multi_disk_backup_pull_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_full_backup_multi_disk_pull_mode,
    vm_with_boot_and_data_disk,
    data_disk_dv_for_cbt_vm,
    storage_class_name_scope_module,
):
    """
    Multi-disk VM restored from full backup (pull mode) and started.

    Returns:
        VirtualMachine: Running restored VM with boot and data disks
    """
    source_disk_size = vm_with_boot_and_data_disk.data_volume_template["spec"]["storage"]["resources"]["requests"][
        "storage"
    ]
    source_volume_names = [DV_DISK, data_disk_dv_for_cbt_vm.name]

    restored_vm = restore_vm_from_backup(
        backup=completed_full_backup_multi_disk_pull_mode,
        restored_vm_name=f"{vm_with_boot_and_data_disk.name}-restored-multi-disk-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        admin_client=admin_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        data_disk_size=DATA_DISK_SIZE,
        source_volume_names=source_volume_names,
    )

    vm_with_boot_and_data_disk.delete(wait=True)

    running_vm(vm=restored_vm)
    mount_cbt_data_disk_on_vm(vm=restored_vm)

    yield restored_vm

    restored_vm.delete(wait=True)


# Live migration backup fixtures


@pytest.fixture(scope="module")
def available_rwx_storage_class_for_cbt(unprivileged_client, available_storage_classes_names):
    """
    RWX storage class available for CBT live migration tests.

    Returns:
        str: Storage class name with RWX access mode
    """
    for storage_class_name in available_storage_classes_names:
        if (
            StorageProfile(client=unprivileged_client, name=storage_class_name).first_claim_property_set_access_modes()[
                0
            ]
            == DataVolume.AccessMode.RWX
        ):
            return storage_class_name
    pytest.fail("No RWX storage class available in the cluster")


@pytest.fixture()
def vm_with_cbt_on_rwx_storage(
    unprivileged_client,
    namespace,
    cbt_label_selectors_configured,
    available_rwx_storage_class_for_cbt,
    rhel9_data_source_scope_session,
):
    """
    VM with CBT enabled on RWX storage, started, and test data written.

    Returns:
        VirtualMachine: Running VM with CBT enabled on RWX storage
    """
    with VirtualMachineForTests(
        name="cbt-rwx-migration-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(client=unprivileged_client, name="rhel.9"),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel9_data_source_scope_session,
            storage_class=available_rwx_storage_class_for_cbt,
        ),
        os_flavor=OS_FLAVOR_RHEL,
        label=CBT_ENABLED_LABEL,
    ) as vm:
        running_vm(vm=vm)
        write_file_via_ssh(vm=vm, filename=CBT_BOOT_DISK_TEST_DATA_FILE, content=CBT_TEST_DATA)
        yield vm


@pytest.fixture()
def backup_tracker_for_rwx_vm(
    unprivileged_client,
    namespace,
    vm_with_cbt_on_rwx_storage,
):
    """
    VirtualMachineBackupTracker for the RWX VM.

    Returns:
        VirtualMachineBackupTracker: Backup tracker for the RWX VM
    """
    with VirtualMachineBackupTracker(
        name=f"{vm_with_cbt_on_rwx_storage.name}-tracker",
        namespace=namespace.name,
        client=unprivileged_client,
        source={
            "apiGroup": "kubevirt.io",
            "kind": "VirtualMachine",
            "name": vm_with_cbt_on_rwx_storage.name,
        },
    ) as tracker:
        yield tracker


@pytest.fixture()
def completed_full_backup_before_migration_push(
    unprivileged_client,
    namespace,
    backup_tracker_for_rwx_vm,
    backup_pvc,
):
    """
    Full backup of RWX VM before migration in push mode, completed.

    Returns:
        VirtualMachineBackup: Completed full backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name="full-backup-before-migration-push",
        namespace=namespace.name,
        client=unprivileged_client,
        pvc_name=backup_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_rwx_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.DONE,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def migrated_vm_with_post_migration_data(
    vm_with_cbt_on_rwx_storage,
    completed_full_backup_before_migration_push,
):
    """
    RWX VM live-migrated with post-migration test data written (push backup chain).

    Returns:
        VirtualMachine: Migrated VM with post-migration test data
    """
    migrate_vm_and_verify(vm=vm_with_cbt_on_rwx_storage)
    write_file_via_ssh(
        vm=vm_with_cbt_on_rwx_storage,
        filename=CBT_POST_MIGRATION_TEST_DATA_FILE,
        content=CBT_POST_MIGRATION_TEST_DATA,
    )
    yield vm_with_cbt_on_rwx_storage


@pytest.fixture()
def completed_incremental_backup_after_migration_push(
    unprivileged_client,
    namespace,
    backup_tracker_for_rwx_vm,
    backup_pvc,
    migrated_vm_with_post_migration_data,
):
    """
    Incremental backup after live migration in push mode, completed.

    Returns:
        VirtualMachineBackup: Completed incremental backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name="incremental-backup-after-migration-push",
        namespace=namespace.name,
        client=unprivileged_client,
        pvc_name=backup_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_rwx_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.DONE,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_after_migration_incremental_push(
    admin_client,
    unprivileged_client,
    namespace,
    completed_incremental_backup_after_migration_push,
    vm_with_cbt_on_rwx_storage,
    backup_pvc,
    available_rwx_storage_class_for_cbt,
):
    """
    RWX VM restored from post-migration incremental backup (push mode) and started.

    Returns:
        VirtualMachine: Running restored VM
    """
    vm_with_cbt_on_rwx_storage.delete(wait=True)

    source_disk_size = vm_with_cbt_on_rwx_storage.data_volume_template["spec"]["storage"]["resources"]["requests"][
        "storage"
    ]

    restored_vm = restore_vm_from_backup(
        backup=completed_incremental_backup_after_migration_push,
        restored_vm_name=f"{vm_with_cbt_on_rwx_storage.name}-restored-after-migration",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=available_rwx_storage_class_for_cbt,
        size=source_disk_size,
        admin_client=admin_client,
        backup_pvc_name=backup_pvc.name,
    )

    running_vm(vm=restored_vm)

    yield restored_vm

    restored_vm.delete(wait=True)


@pytest.fixture()
def completed_full_backup_before_migration_pull(
    unprivileged_client,
    namespace,
    backup_tracker_for_rwx_vm,
    scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
):
    """
    Full backup of RWX VM before migration in pull mode, completed.

    Returns:
        VirtualMachineBackup: Completed full backup with export endpoint ready
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name="full-backup-before-migration-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=scratch_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_rwx_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.EXPORT_READY,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def migrated_vm_with_post_migration_data_pull_mode(
    vm_with_cbt_on_rwx_storage,
    completed_full_backup_before_migration_pull,
):
    """
    RWX VM live-migrated with post-migration test data written (pull backup chain).

    Returns:
        VirtualMachine: Migrated VM with post-migration test data
    """
    migrate_vm_and_verify(vm=vm_with_cbt_on_rwx_storage)
    write_file_via_ssh(
        vm=vm_with_cbt_on_rwx_storage,
        filename=CBT_POST_MIGRATION_TEST_DATA_FILE,
        content=CBT_POST_MIGRATION_TEST_DATA,
    )
    release_pull_mode_backup(backup=completed_full_backup_before_migration_pull)
    yield vm_with_cbt_on_rwx_storage


@pytest.fixture()
def completed_incremental_backup_after_migration_pull(
    unprivileged_client,
    namespace,
    backup_tracker_for_rwx_vm,
    scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
    migrated_vm_with_post_migration_data_pull_mode,
):
    """
    Incremental backup after live migration in pull mode, completed.

    Returns:
        VirtualMachineBackup: Completed incremental backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name="incremental-backup-after-migration-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=scratch_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_rwx_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.EXPORT_READY,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_after_migration_incremental_pull(
    admin_client,
    unprivileged_client,
    namespace,
    completed_incremental_backup_after_migration_pull,
    vm_with_cbt_on_rwx_storage,
    available_rwx_storage_class_for_cbt,
):
    """
    RWX VM restored from post-migration incremental backup (pull mode) and started.

    Returns:
        VirtualMachine: Running restored VM
    """
    source_disk_size = vm_with_cbt_on_rwx_storage.data_volume_template["spec"]["storage"]["resources"]["requests"][
        "storage"
    ]

    restored_vm = restore_vm_from_backup(
        backup=completed_incremental_backup_after_migration_pull,
        restored_vm_name=f"{vm_with_cbt_on_rwx_storage.name}-restored-after-migration-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        admin_client=admin_client,
        storage_class=available_rwx_storage_class_for_cbt,
        size=source_disk_size,
    )

    vm_with_cbt_on_rwx_storage.delete(wait=True)

    running_vm(vm=restored_vm)

    yield restored_vm

    restored_vm.delete(wait=True)


# Hotplug backup fixtures


@pytest.fixture(scope="module")
def declarative_hotplug_volumes_feature_gate_enabled(
    hyperconverged_resource_scope_module,
    admin_client,
    hco_namespace,
):
    """
    Enable declarativeHotplugVolumes feature gate in HyperConverged CR.

    Yields while the feature gate remains enabled.
    """
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: {"spec": {"featureGates": {"declarativeHotplugVolumes": True}}},
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=admin_client,
        hco_namespace=hco_namespace.name,
    ):
        yield


@pytest.fixture()
def blank_hotplug_disk_dv(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
):
    """
    Blank DataVolume for hotplug disk testing.

    Returns:
        DataVolume: Blank DataVolume for hotplug
    """
    with create_dv(
        source="blank",
        dv_name="cbt-hotplug-disk-dv",
        client=unprivileged_client,
        namespace=namespace.name,
        size=DATA_DISK_SIZE,
        storage_class=storage_class_name_scope_module,
    ) as data_volume:
        yield data_volume


@pytest.fixture()
def vm_with_hotplugged_disk_and_data(
    namespace,
    declarative_hotplug_volumes_feature_gate_enabled,
    vm_with_cbt_label,
    blank_hotplug_disk_dv,
):
    """
    VM with hotplugged disk mounted and test data written.

    Returns:
        VirtualMachine: Running VM with hotplugged disk test data
    """
    with virtctl_volume(
        action="add",
        namespace=namespace.name,
        vm_name=vm_with_cbt_label.name,
        volume_name=blank_hotplug_disk_dv.name,
        persist=True,
    ) as hotplug_result:
        status, out, err = hotplug_result
        assert status, f"Failed to add volume to VM, out: {out}, err: {err}."
        wait_for_vm_volume_ready(
            vm=vm_with_cbt_label,
            volume_name=blank_hotplug_disk_dv.name,
        )
        run_ssh_commands(
            host=vm_with_cbt_label.ssh_exec,
            commands=[
                shlex.split(f"sudo mkdir -p {CBT_HOTPLUG_DISK_MOUNT_PATH}"),
                shlex.split(f"sudo mkfs.ext4 {CBT_HOTPLUG_DISK_DEVICE}"),
                shlex.split(f"sudo mount {CBT_HOTPLUG_DISK_DEVICE} {CBT_HOTPLUG_DISK_MOUNT_PATH}"),
            ],
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )
        chown_mount_path_for_vm_user(vm=vm_with_cbt_label, mount_path=CBT_HOTPLUG_DISK_MOUNT_PATH)
        write_file_via_ssh(
            vm=vm_with_cbt_label,
            filename=CBT_HOTPLUG_DISK_TEST_DATA_FILE,
            content=CBT_HOTPLUG_DISK_TEST_DATA,
        )
        yield vm_with_cbt_label


@pytest.fixture()
def backup_tracker_for_hotplug_vm(
    unprivileged_client,
    namespace,
    vm_with_hotplugged_disk_and_data,
):
    """
    VirtualMachineBackupTracker for the hotplug VM.

    Returns:
        VirtualMachineBackupTracker: Backup tracker for the hotplug VM
    """
    with VirtualMachineBackupTracker(
        name=f"{vm_with_hotplugged_disk_and_data.name}-tracker",
        namespace=namespace.name,
        client=unprivileged_client,
        source={
            "apiGroup": "kubevirt.io",
            "kind": "VirtualMachine",
            "name": vm_with_hotplugged_disk_and_data.name,
        },
    ) as tracker:
        yield tracker


@pytest.fixture()
def completed_full_backup_hotplug_push(
    unprivileged_client,
    namespace,
    backup_tracker_for_hotplug_vm,
    backup_pvc,
):
    """
    Full backup of hotplug VM in push mode, completed.

    Returns:
        VirtualMachineBackup: Completed full backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name="full-backup-hotplug-push",
        namespace=namespace.name,
        client=unprivileged_client,
        pvc_name=backup_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_hotplug_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.DONE,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_hotplug_push(
    admin_client,
    unprivileged_client,
    namespace,
    completed_full_backup_hotplug_push,
    vm_with_hotplugged_disk_and_data,
    blank_hotplug_disk_dv,
    backup_pvc,
    storage_class_name_scope_module,
):
    """
    Hotplug VM restored from full backup (push mode) and started.

    Returns:
        VirtualMachine: Running restored VM with boot and hotplug disks
    """
    source_volume_names = get_vm_disk_volume_names(vm=vm_with_hotplugged_disk_and_data)
    vm_with_hotplugged_disk_and_data.delete(wait=True)
    blank_hotplug_disk_dv.delete(wait=True)

    source_disk_size = vm_with_hotplugged_disk_and_data.data_volume_template["spec"]["storage"]["resources"][
        "requests"
    ]["storage"]

    restored_vm = restore_vm_from_backup(
        backup=completed_full_backup_hotplug_push,
        restored_vm_name=f"{vm_with_hotplugged_disk_and_data.name}-restored-hotplug",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        admin_client=admin_client,
        backup_pvc_name=backup_pvc.name,
        data_disk_size=DATA_DISK_SIZE,
        source_volume_names=source_volume_names,
    )

    running_vm(vm=restored_vm)
    mount_cbt_hotplug_disk_on_vm(vm=restored_vm)

    yield restored_vm

    restored_vm.delete(wait=True)


@pytest.fixture()
def completed_full_backup_hotplug_pull(
    unprivileged_client,
    namespace,
    backup_tracker_for_hotplug_vm,
    scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
):
    """
    Full backup of hotplug VM in pull mode, completed.

    Returns:
        VirtualMachineBackup: Completed full backup with export endpoint ready
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name="full-backup-hotplug-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=scratch_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_hotplug_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.EXPORT_READY,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_hotplug_pull(
    admin_client,
    unprivileged_client,
    namespace,
    completed_full_backup_hotplug_pull,
    vm_with_hotplugged_disk_and_data,
    blank_hotplug_disk_dv,
    storage_class_name_scope_module,
):
    """
    Hotplug VM restored from full backup (pull mode) and started.

    Returns:
        VirtualMachine: Running restored VM with boot and hotplug disks
    """
    source_volume_names = get_vm_disk_volume_names(vm=vm_with_hotplugged_disk_and_data)
    source_disk_size = vm_with_hotplugged_disk_and_data.data_volume_template["spec"]["storage"]["resources"][
        "requests"
    ]["storage"]

    restored_vm = restore_vm_from_backup(
        backup=completed_full_backup_hotplug_pull,
        restored_vm_name=f"{vm_with_hotplugged_disk_and_data.name}-restored-hotplug-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        admin_client=admin_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        data_disk_size=DATA_DISK_SIZE,
        source_volume_names=source_volume_names,
    )

    vm_with_hotplugged_disk_and_data.delete(wait=True)
    blank_hotplug_disk_dv.delete(wait=True)

    running_vm(vm=restored_vm)
    mount_cbt_hotplug_disk_on_vm(vm=restored_vm)

    yield restored_vm

    restored_vm.delete(wait=True)


# Negative backup fixtures


@pytest.fixture()
def undersized_backup_pvc(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
):
    """
    Undersized PVC for negative push-mode backup testing.

    Returns:
        PersistentVolumeClaim: 1Gi backup PVC
    """
    with PersistentVolumeClaim(
        name="cbt-undersized-backup-pvc",
        namespace=namespace.name,
        client=unprivileged_client,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=UNDERSIZED_BACKUP_PVC_SIZE,
        storage_class=storage_class_name_scope_module,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as pvc:
        yield pvc


@pytest.fixture()
def failed_full_backup_push_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_vm,
    undersized_backup_pvc,
    vm_with_cbt_label,
):
    """
    Failed full backup in push mode due to undersized PVC.

    Returns:
        VirtualMachineBackup: Failed backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name="failed-full-backup-push",
        namespace=namespace.name,
        client=unprivileged_client,
        pvc_name=undersized_backup_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_vm.name),
    ) as backup:
        wait_for_backup_to_fail(backup=backup, timeout=TIMEOUT_10MIN)
        yield backup


@pytest.fixture()
def vm_still_accessible_after_failed_push_backup(
    failed_full_backup_push_mode,
    vm_with_cbt_label,
):
    """
    Boot disk test data readable from VM after failed push backup.

    Returns:
        str: Content of the test data file from the VM
    """
    return read_file_content_from_vm(
        vm=vm_with_cbt_label,
        file_path=CBT_BOOT_DISK_TEST_DATA_FILE,
    )


@pytest.fixture()
def undersized_scratch_pvc(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
):
    """
    Undersized scratch PVC for negative pull-mode backup testing.

    Returns:
        PersistentVolumeClaim: 1Gi scratch PVC
    """
    with PersistentVolumeClaim(
        name="cbt-undersized-scratch-pvc",
        namespace=namespace.name,
        client=unprivileged_client,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=UNDERSIZED_BACKUP_PVC_SIZE,
        storage_class=storage_class_name_scope_module,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as pvc:
        yield pvc


@pytest.fixture()
def failed_full_backup_pull_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_vm,
    undersized_scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
    vm_with_cbt_label,
):
    """
    Failed full backup in pull mode due to undersized scratch PVC.

    Returns:
        VirtualMachineBackup: Failed backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name="failed-full-backup-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=undersized_scratch_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_vm.name),
    ) as backup:
        wait_for_backup_to_fail(backup=backup, timeout=TIMEOUT_10MIN)
        yield backup


@pytest.fixture()
def vm_still_accessible_after_failed_pull_backup(
    failed_full_backup_pull_mode,
    vm_with_cbt_label,
):
    """
    Boot disk test data readable from VM after failed pull backup.

    Returns:
        str: Content of the test data file from the VM
    """
    return read_file_content_from_vm(
        vm=vm_with_cbt_label,
        file_path=CBT_BOOT_DISK_TEST_DATA_FILE,
    )


# Concurrent backup fixtures


@pytest.fixture()
def five_cbt_vms_with_test_data(
    unprivileged_client,
    namespace,
    cbt_label_selectors_configured,
    storage_class_name_scope_module,
    rhel9_data_source_scope_session,
):
    """
    Five running VMs with CBT enabled and test data written.

    Returns:
        list[VirtualMachine]: Running VMs with test data
    """
    vms: list[VirtualMachineForTests] = []
    with ExitStack() as stack:
        for vm_index in range(CONCURRENT_CBT_VM_COUNT):
            vm = stack.enter_context(
                VirtualMachineForTests(
                    name=f"cbt-concurrent-vm-{vm_index}",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name=U1_SMALL),
                    vm_preference=VirtualMachineClusterPreference(client=unprivileged_client, name="rhel.9"),
                    data_volume_template=data_volume_template_with_source_ref_dict(
                        data_source=rhel9_data_source_scope_session,
                        storage_class=storage_class_name_scope_module,
                    ),
                    os_flavor=OS_FLAVOR_RHEL,
                    label=CBT_ENABLED_LABEL,
                )
            )
            running_vm(vm=vm)
            write_file_via_ssh(vm=vm, filename=CBT_BOOT_DISK_TEST_DATA_FILE, content=CBT_TEST_DATA)
            vms.append(vm)
        yield vms


@pytest.fixture()
def five_backup_trackers(
    unprivileged_client,
    namespace,
    five_cbt_vms_with_test_data,
):
    """
    Backup trackers for five concurrent CBT VMs.

    Returns:
        list[VirtualMachineBackupTracker]: Backup trackers
    """
    trackers: list[VirtualMachineBackupTracker] = []
    with ExitStack() as stack:
        for vm in five_cbt_vms_with_test_data:
            tracker = stack.enter_context(
                VirtualMachineBackupTracker(
                    name=f"{vm.name}-tracker",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    source={
                        "apiGroup": "kubevirt.io",
                        "kind": "VirtualMachine",
                        "name": vm.name,
                    },
                )
            )
            trackers.append(tracker)
        yield trackers


@pytest.fixture()
def five_backup_pvcs(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
    five_cbt_vms_with_test_data,
):
    """
    Backup PVCs for five concurrent CBT VMs.

    Returns:
        list[PersistentVolumeClaim]: Backup PVCs
    """
    pvcs: list[PersistentVolumeClaim] = []
    with ExitStack() as stack:
        for vm in five_cbt_vms_with_test_data:
            pvc = stack.enter_context(
                PersistentVolumeClaim(
                    name=f"{vm.name}-backup-pvc",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    accessmodes=PersistentVolumeClaim.AccessMode.RWO,
                    size="40Gi",
                    storage_class=storage_class_name_scope_module,
                    volume_mode=DataVolume.VolumeMode.FILE,
                )
            )
            pvcs.append(pvc)
        yield pvcs


@pytest.fixture()
def five_completed_full_backups_push_mode(
    unprivileged_client,
    namespace,
    five_backup_trackers,
    five_backup_pvcs,
):
    """
    Full backups in push mode for five concurrent VMs, all completed.

    Returns:
        list[VirtualMachineBackup]: Completed backups
    """
    backups: list[VirtualMachineBackup] = []
    with ExitStack() as stack:
        for tracker, pvc in zip(five_backup_trackers, five_backup_pvcs, strict=True):
            backup = stack.enter_context(
                VirtualMachineBackup(
                    mode=VirtualMachineBackup.Mode.PUSH,
                    name=f"{tracker.name}-full-backup-push",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    pvc_name=pvc.name,
                    force_full_backup=True,
                    source=backup_tracker_source_dict(tracker_name=tracker.name),
                )
            )
            backup.wait_for_condition(
                condition="Done",
                status="True",
                timeout=TIMEOUT_10MIN,
            )
            backups.append(backup)
        yield backups


@pytest.fixture()
def five_restored_vms_push_mode(
    admin_client,
    unprivileged_client,
    namespace,
    five_completed_full_backups_push_mode,
    five_cbt_vms_with_test_data,
    five_backup_pvcs,
    storage_class_name_scope_module,
):
    """
    Five VMs restored from full backups (push mode) and started.

    Returns:
        list[VirtualMachine]: Running restored VMs
    """
    restored_vms: list[VirtualMachineForTests] = []
    for vm, backup, backup_pvc_for_vm in zip(
        five_cbt_vms_with_test_data,
        five_completed_full_backups_push_mode,
        five_backup_pvcs,
        strict=True,
    ):
        source_disk_size = vm.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"]
        vm.delete(wait=True)
        restored_vm = restore_vm_from_backup(
            backup=backup,
            restored_vm_name=f"{vm.name}-restored",
            namespace=namespace.name,
            client=unprivileged_client,
            storage_class=storage_class_name_scope_module,
            size=source_disk_size,
            admin_client=admin_client,
            backup_pvc_name=backup_pvc_for_vm.name,
        )
        running_vm(vm=restored_vm)
        restored_vms.append(restored_vm)

    yield restored_vms

    for restored_vm in restored_vms:
        restored_vm.delete(wait=True)


@pytest.fixture()
def test_data_from_five_restored_vms_push_mode(five_restored_vms_push_mode):
    """
    Boot disk test data from all five restored VMs (push mode).

    Returns:
        list[str]: Test data content from each restored VM
    """
    return [
        read_file_content_from_vm(vm=restored_vm, file_path=CBT_BOOT_DISK_TEST_DATA_FILE)
        for restored_vm in five_restored_vms_push_mode
    ]


@pytest.fixture()
def five_scratch_pvcs(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
    five_cbt_vms_with_test_data,
):
    """
    Scratch PVCs for five concurrent pull-mode backups.

    Returns:
        list[PersistentVolumeClaim]: Scratch PVCs
    """
    pvcs: list[PersistentVolumeClaim] = []
    with ExitStack() as stack:
        for vm in five_cbt_vms_with_test_data:
            pvc = stack.enter_context(
                PersistentVolumeClaim(
                    name=f"{vm.name}-scratch-pvc",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    accessmodes=PersistentVolumeClaim.AccessMode.RWO,
                    size="40Gi",
                    storage_class=storage_class_name_scope_module,
                    volume_mode=DataVolume.VolumeMode.FILE,
                )
            )
            pvcs.append(pvc)
        yield pvcs


@pytest.fixture()
def five_completed_full_backups_pull_mode(
    unprivileged_client,
    namespace,
    five_backup_trackers,
    five_scratch_pvcs,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
):
    """
    Full backups in pull mode for five concurrent VMs, all completed.

    Returns:
        list[VirtualMachineBackup]: Completed backups
    """
    backups: list[VirtualMachineBackup] = []
    with ExitStack() as stack:
        for tracker, scratch_pvc_for_vm in zip(five_backup_trackers, five_scratch_pvcs, strict=True):
            backup = stack.enter_context(
                VirtualMachineBackup(
                    mode=VirtualMachineBackup.Mode.PULL,
                    name=f"{tracker.name}-full-backup-pull",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    token_secret_ref=pull_mode_token_secret_name,
                    pvc_name=scratch_pvc_for_vm.name,
                    force_full_backup=True,
                    source=backup_tracker_source_dict(tracker_name=tracker.name),
                )
            )
            backup.wait_for_condition(
                condition="ExportReady",
                status="True",
                timeout=TIMEOUT_10MIN,
            )
            backups.append(backup)
        yield backups


@pytest.fixture()
def five_restored_vms_pull_mode(
    admin_client,
    unprivileged_client,
    namespace,
    five_completed_full_backups_pull_mode,
    five_cbt_vms_with_test_data,
    storage_class_name_scope_module,
):
    """
    Five VMs restored from full backups (pull mode) and started.

    Returns:
        list[VirtualMachine]: Running restored VMs
    """
    restored_vms: list[VirtualMachineForTests] = []
    for vm, backup in zip(five_cbt_vms_with_test_data, five_completed_full_backups_pull_mode, strict=True):
        source_disk_size = vm.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"]
        vm.delete(wait=True)
        restored_vm = restore_vm_from_backup(
            backup=backup,
            restored_vm_name=f"{vm.name}-restored-pull",
            namespace=namespace.name,
            client=unprivileged_client,
            admin_client=admin_client,
            storage_class=storage_class_name_scope_module,
            size=source_disk_size,
        )
        running_vm(vm=restored_vm)
        restored_vms.append(restored_vm)

    yield restored_vms

    for restored_vm in restored_vms:
        restored_vm.delete(wait=True)


@pytest.fixture()
def test_data_from_five_restored_vms_pull_mode(five_restored_vms_pull_mode):
    """
    Boot disk test data from all five restored VMs (pull mode).

    Returns:
        list[str]: Test data content from each restored VM
    """
    return [
        read_file_content_from_vm(vm=restored_vm, file_path=CBT_BOOT_DISK_TEST_DATA_FILE)
        for restored_vm in five_restored_vms_pull_mode
    ]


# Windows VM backup fixtures


@pytest.fixture()
def windows_dv_for_cbt(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
):
    """
    Windows 2022 DataVolume for CBT testing.

    Returns:
        dict: DataVolume template dictionary
    """
    with create_windows2022_dv_from_registry(
        dv_name="cbt-windows-dv",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
    ) as dv_dict:
        yield dv_dict


@pytest.fixture()
def windows_vm_with_cbt(
    unprivileged_client,
    namespace,
    windows_dv_for_cbt,
    modern_cpu_for_migration,
):
    """
    Windows VM with CBT enabled, started, and test data written.

    Returns:
        VirtualMachine: Running Windows VM with CBT enabled
    """
    with VirtualMachineForTests(
        name="cbt-windows-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name=U1_LARGE),
        vm_preference=VirtualMachineClusterPreference(client=unprivileged_client, name=WINDOWS_2K22_PREFERENCE),
        data_volume_template=windows_dv_for_cbt,
        cpu_model=modern_cpu_for_migration,
        label=CBT_ENABLED_LABEL,
    ) as vm:
        running_vm(vm=vm)
        wait_for_windows_vm(vm=vm, version="2022")
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=[
                shlex.split(
                    f'powershell -command "New-Item -ItemType Directory -Force -Path {CBT_WINDOWS_TEST_USER_DIR}"'
                ),
            ],
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )
        write_file_windows_vm(
            vm=vm,
            file_path=CBT_WINDOWS_TEST_DATA_FILE,
            content=CBT_WINDOWS_TEST_DATA,
        )
        yield vm


@pytest.fixture()
def backup_tracker_for_windows_vm(
    unprivileged_client,
    namespace,
    windows_vm_with_cbt,
):
    """
    VirtualMachineBackupTracker for the Windows VM.

    Returns:
        VirtualMachineBackupTracker: Backup tracker for the Windows VM
    """
    with VirtualMachineBackupTracker(
        name=f"{windows_vm_with_cbt.name}-tracker",
        namespace=namespace.name,
        client=unprivileged_client,
        source={
            "apiGroup": "kubevirt.io",
            "kind": "VirtualMachine",
            "name": windows_vm_with_cbt.name,
        },
    ) as tracker:
        yield tracker


@pytest.fixture()
def completed_full_backup_windows_push_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_windows_vm,
    backup_pvc,
):
    """
    Full backup of Windows VM in push mode, completed.

    Returns:
        VirtualMachineBackup: Completed full backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name="full-backup-windows-push",
        namespace=namespace.name,
        client=unprivileged_client,
        pvc_name=backup_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_windows_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.DONE,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_full_backup_windows_push_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_full_backup_windows_push_mode,
    windows_vm_with_cbt,
    backup_pvc,
    storage_class_name_scope_module,
):
    """
    Windows VM restored from full backup (push mode) and started.

    Returns:
        VirtualMachine: Running restored Windows VM
    """
    windows_vm_with_cbt.delete(wait=True)

    source_disk_size = windows_vm_with_cbt.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"]

    restored_vm = restore_vm_from_backup(
        backup=completed_full_backup_windows_push_mode,
        restored_vm_name=f"{windows_vm_with_cbt.name}-restored",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        admin_client=admin_client,
        backup_pvc_name=backup_pvc.name,
        os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        vm_preference_name=WINDOWS_2K22_PREFERENCE,
        vm_instance_type_name=U1_LARGE,
    )

    running_vm(vm=restored_vm)
    wait_for_windows_vm(vm=restored_vm, version="2022")

    yield restored_vm

    restored_vm.delete(wait=True)


@pytest.fixture()
def windows_test_data_from_restored_vm_push_mode(restored_vm_from_full_backup_windows_push_mode):
    """
    Windows test data verified on restored VM (push mode).

    Returns:
        str: Expected Windows test data content
    """
    verify_file_in_windows_vm(
        windows_vm=restored_vm_from_full_backup_windows_push_mode,
        file_name_with_path=CBT_WINDOWS_TEST_DATA_FILE,
        file_content=CBT_WINDOWS_TEST_DATA,
    )
    return CBT_WINDOWS_TEST_DATA


@pytest.fixture()
def completed_full_backup_windows_pull_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_windows_vm,
    scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
):
    """
    Full backup of Windows VM in pull mode, completed.

    Returns:
        VirtualMachineBackup: Completed full backup with export endpoint ready
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name="full-backup-windows-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=scratch_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_windows_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.EXPORT_READY,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_full_backup_windows_pull_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_full_backup_windows_pull_mode,
    windows_vm_with_cbt,
    storage_class_name_scope_module,
):
    """
    Windows VM restored from full backup (pull mode) and started.

    Returns:
        VirtualMachine: Running restored Windows VM
    """
    source_disk_size = windows_vm_with_cbt.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"]

    restored_vm = restore_vm_from_backup(
        backup=completed_full_backup_windows_pull_mode,
        restored_vm_name=f"{windows_vm_with_cbt.name}-restored-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        admin_client=admin_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        vm_preference_name=WINDOWS_2K22_PREFERENCE,
        vm_instance_type_name=U1_LARGE,
    )

    windows_vm_with_cbt.delete(wait=True)

    running_vm(vm=restored_vm)
    wait_for_windows_vm(vm=restored_vm, version="2022")

    yield restored_vm

    restored_vm.delete(wait=True)


@pytest.fixture()
def windows_test_data_from_restored_vm_pull_mode(restored_vm_from_full_backup_windows_pull_mode):
    """
    Windows test data verified on restored VM (pull mode).

    Returns:
        str: Expected Windows test data content
    """
    verify_file_in_windows_vm(
        windows_vm=restored_vm_from_full_backup_windows_pull_mode,
        file_name_with_path=CBT_WINDOWS_TEST_DATA_FILE,
        file_content=CBT_WINDOWS_TEST_DATA,
    )
    return CBT_WINDOWS_TEST_DATA


@pytest.fixture()
def windows_incremental_test_data_written(
    windows_vm_with_cbt,
    completed_full_backup_windows_push_mode,
):
    """
    Incremental test data written to Windows VM after full backup (push chain).

    Returns:
        VirtualMachine: Windows VM with incremental test data written
    """
    write_file_windows_vm(
        vm=windows_vm_with_cbt,
        file_path=CBT_WINDOWS_INCREMENTAL_TEST_DATA_FILE,
        content=CBT_WINDOWS_INCREMENTAL_TEST_DATA,
    )
    yield windows_vm_with_cbt


@pytest.fixture()
def completed_incremental_backup_windows_push_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_windows_vm,
    backup_pvc,
    windows_incremental_test_data_written,
):
    """
    Incremental backup of Windows VM in push mode, completed.

    Returns:
        VirtualMachineBackup: Completed incremental backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PUSH,
        name="incremental-backup-windows-push",
        namespace=namespace.name,
        client=unprivileged_client,
        pvc_name=backup_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_windows_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.DONE,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_incremental_backup_windows_push_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_incremental_backup_windows_push_mode,
    windows_vm_with_cbt,
    backup_pvc,
    storage_class_name_scope_module,
):
    """
    Windows VM restored from incremental backup (push mode) and started.

    Returns:
        VirtualMachine: Running restored Windows VM
    """
    windows_vm_with_cbt.delete(wait=True)

    source_disk_size = windows_vm_with_cbt.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"]

    restored_vm = restore_vm_from_backup(
        backup=completed_incremental_backup_windows_push_mode,
        restored_vm_name=f"{windows_vm_with_cbt.name}-restored-incremental",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        admin_client=admin_client,
        backup_pvc_name=backup_pvc.name,
        os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        vm_preference_name=WINDOWS_2K22_PREFERENCE,
        vm_instance_type_name=U1_LARGE,
    )

    running_vm(vm=restored_vm)
    wait_for_windows_vm(vm=restored_vm, version="2022")

    yield restored_vm

    restored_vm.delete(wait=True)


@pytest.fixture()
def windows_incremental_test_data_written_pull_mode(
    windows_vm_with_cbt,
    completed_full_backup_windows_pull_mode,
):
    """
    Incremental test data written to Windows VM after full backup (pull chain).

    Returns:
        VirtualMachine: Windows VM with incremental test data written
    """
    write_file_windows_vm(
        vm=windows_vm_with_cbt,
        file_path=CBT_WINDOWS_INCREMENTAL_TEST_DATA_FILE,
        content=CBT_WINDOWS_INCREMENTAL_TEST_DATA,
    )
    release_pull_mode_backup(backup=completed_full_backup_windows_pull_mode)
    yield windows_vm_with_cbt


@pytest.fixture()
def completed_incremental_backup_windows_pull_mode(
    unprivileged_client,
    namespace,
    backup_tracker_for_windows_vm,
    scratch_pvc,
    pull_mode_token_secret,
    pull_mode_token_secret_name,
    windows_incremental_test_data_written_pull_mode,
):
    """
    Incremental backup of Windows VM in pull mode, completed.

    Returns:
        VirtualMachineBackup: Completed incremental backup
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name="incremental-backup-windows-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret_name,
        pvc_name=scratch_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source_dict(tracker_name=backup_tracker_for_windows_vm.name),
    ) as backup:
        backup.wait_for_condition(
            condition=backup.Condition.EXPORT_READY,
            status=backup.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield backup


@pytest.fixture()
def restored_vm_from_incremental_backup_windows_pull_mode(
    admin_client,
    unprivileged_client,
    namespace,
    completed_incremental_backup_windows_pull_mode,
    windows_vm_with_cbt,
    storage_class_name_scope_module,
):
    """
    Windows VM restored from incremental backup (pull mode) and started.

    Returns:
        VirtualMachine: Running restored Windows VM
    """
    source_disk_size = windows_vm_with_cbt.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"]

    restored_vm = restore_vm_from_backup(
        backup=completed_incremental_backup_windows_pull_mode,
        restored_vm_name=f"{windows_vm_with_cbt.name}-restored-incremental-pull",
        namespace=namespace.name,
        client=unprivileged_client,
        admin_client=admin_client,
        storage_class=storage_class_name_scope_module,
        size=source_disk_size,
        os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        vm_preference_name=WINDOWS_2K22_PREFERENCE,
        vm_instance_type_name=U1_LARGE,
    )

    windows_vm_with_cbt.delete(wait=True)

    running_vm(vm=restored_vm)
    wait_for_windows_vm(vm=restored_vm, version="2022")

    yield restored_vm

    restored_vm.delete(wait=True)
