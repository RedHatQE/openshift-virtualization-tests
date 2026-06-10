"""
CBT (Changed Block Tracking) test fixtures.

Fixtures for setting up VMs, backups, and restores for CBT testing.
"""

import secrets
import shlex
from contextlib import ExitStack

import pytest
from kubernetes.utils.quantity import parse_quantity
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
    CBT_ENABLED_LABEL,
    CBT_INCREMENTAL_TEST_DATA,
    CBT_INCREMENTAL_TEST_DATA_FILE,
    CBT_TEST_DATA,
    backup_tracker_source_dict,
    read_file_content_from_vm,
    restore_vm_from_backup,
)
from utilities.constants import (
    OS_FLAVOR_RHEL,
    RHEL9_PREFERENCE,
    TIMEOUT_10MIN,
    U1_SMALL,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import (
    data_volume_template_with_source_ref_dict,
    write_file_via_ssh,
)
from utilities.virt import VirtualMachineForTests, running_vm

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
