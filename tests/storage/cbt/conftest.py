"""CBT backup fixtures (backup success only)."""

import secrets
from contextlib import ExitStack

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.secret import Secret
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_backup import VirtualMachineBackup
from ocp_resources.virtual_machine_backup_tracker import VirtualMachineBackupTracker
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from tests.storage.cbt.constants import (
    CBT_BOOT_DISK_TEST_DATA_FILE,
    CBT_DATA_DISK_TEST_DATA,
    CBT_ENABLED_LABEL,
    CBT_TEST_DATA,
)
from tests.storage.cbt.utils import (
    CbtVmWithDataDisks,
    cbt_pvc_size_for_vm,
    data_disk_name,
    deploy_cbt_pull_backup,
    guest_device_path_for_volume,
    incremental_test_data,
    incremental_test_data_file,
    wait_for_pull_backup_export_deleted,
    wait_for_pull_backup_export_ready,
    wait_for_push_backup_complete,
    wait_for_vm_cbt_enabled,
)
from utilities.constants.images import OS_FLAVOR_RHEL
from utilities.constants.instance_types import RHEL9_PREFERENCE, U1_SMALL
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import (
    data_volume_template_with_source_ref_dict,
    write_file_via_ssh,
)
from utilities.virt import running_vm


@pytest.fixture(scope="module")
def cbt_hco_configured(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_module,
):
    """
    Enable incremental backup and CBT VM label selectors in HyperConverged CR.

    Yields while both settings remain configured.
    """
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: {
                "spec": {
                    "featureGates": {"incrementalBackup": True},
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
    cbt_hco_configured,
    storage_class_name_scope_module,
    rhel9_data_source_scope_session,
    unique_suffix,
):
    """
    VM with CBT enabled, started, and test data written.

    request.param (dict):
        name: VM name prefix.
        data_disk_count: Optional int (default 0). Number of blank data disks (named
            "cbt-datadisk-<index>-<unique_suffix>") to attach before first start (avoiding a
            restart) and write test data to, in addition to the boot disk.

    Returns:
        VirtualMachine: Running VM with CBT enabled and test data written
    """
    data_disk_count = request.param.get("data_disk_count", 0)
    with CbtVmWithDataDisks(
        name=f"{request.param['name']}-{unique_suffix}",
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
        data_disk_storage_class_name=storage_class_name_scope_module,
        data_disk_count=data_disk_count,
        unique_suffix=unique_suffix,
    ) as vm:
        running_vm(vm=vm)
        wait_for_vm_cbt_enabled(vm=vm)
        write_file_via_ssh(vm=vm, filename=CBT_BOOT_DISK_TEST_DATA_FILE, content=CBT_TEST_DATA)
        for disk_index in range(1, data_disk_count + 1):
            volume_name = data_disk_name(index=disk_index, unique_suffix=unique_suffix)
            write_file_via_ssh(
                vm=vm,
                filename=guest_device_path_for_volume(vm=vm, volume_name=volume_name),
                content=CBT_DATA_DISK_TEST_DATA,
                use_sudo=True,
            )
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
            "kind": VirtualMachine.kind,
            "name": vm_with_cbt_label.name,
        },
    ) as tracker:
        yield tracker


@pytest.fixture()
def backup_tracker_source(backup_tracker_for_vm):
    """
    VirtualMachineBackup.spec.source reference for the VM backup tracker.

    Returns:
        dict: Backup tracker source reference
    """
    return {
        "apiGroup": VirtualMachineBackupTracker.api_group,
        "kind": VirtualMachineBackupTracker.kind,
        "name": backup_tracker_for_vm.name,
    }


@pytest.fixture()
def push_backup_pvc(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    storage_class_name_scope_module,
    unique_suffix,
):
    """
    PVC for storing push-mode backup output.

    Returns:
        PersistentVolumeClaim: PVC for push-mode backup storage
    """
    with PersistentVolumeClaim(
        name=f"cbt-backup-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=cbt_pvc_size_for_vm(vm=vm_with_cbt_label),
        storage_class=storage_class_name_scope_module,
        volume_mode=PersistentVolumeClaim.VolumeMode.FILE,
    ) as pvc:
        yield pvc


@pytest.fixture()
def pull_backup_staging_pvc(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    storage_class_name_scope_module,
    unique_suffix,
):
    """
    Controller-side staging PVC for pull-mode backup export.

    Returns:
        PersistentVolumeClaim: Staging PVC for the pull-mode export
    """
    with PersistentVolumeClaim(
        name=f"cbt-staging-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=cbt_pvc_size_for_vm(vm=vm_with_cbt_label),
        storage_class=storage_class_name_scope_module,
        volume_mode=PersistentVolumeClaim.VolumeMode.FILE,
    ) as pvc:
        yield pvc


@pytest.fixture()
def pull_mode_token_secret(
    unprivileged_client,
    namespace,
    unique_suffix,
):
    """
    User-provided export token secret for pull-mode backup authentication.

    Returns:
        Secret: Pull-mode token secret
    """
    with Secret(
        name=f"cbt-pull-token-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        string_data={"token": secrets.token_urlsafe(nbytes=16)},
    ) as secret:
        yield secret


@pytest.fixture()
def completed_push_backup_chain(
    request,
    unprivileged_client,
    namespace,
    push_backup_pvc,
    vm_with_cbt_label,
    backup_tracker_source,
    unique_suffix,
):
    """
    Sequential push-mode backup chain: a full backup followed by incremental backups.

    request.param (dict):
        incremental_count: Number of incremental backups to perform after the full backup.
            Use 0 for a full-backup-only chain.

    Side effects:
        Writes new test data to the VM before each incremental backup.

    Returns:
        list[VirtualMachineBackup]: Every backup in the chain, in order (full backup first,
            followed by each incremental backup).
    """
    incremental_count = request.param["incremental_count"]
    with ExitStack() as stack:
        backups = []
        full_backup = stack.enter_context(
            cm=VirtualMachineBackup(
                mode=VirtualMachineBackup.Mode.PUSH,
                name=f"full-push-{unique_suffix}",
                namespace=namespace.name,
                client=unprivileged_client,
                pvc_name=push_backup_pvc.name,
                force_full_backup=True,
                source=backup_tracker_source,
            )
        )
        wait_for_push_backup_complete(backup=full_backup)
        backups.append(full_backup)
        for incremental_index in range(1, incremental_count + 1):
            write_file_via_ssh(
                vm=vm_with_cbt_label,
                filename=incremental_test_data_file(index=incremental_index),
                content=incremental_test_data(index=incremental_index),
            )
            incremental_backup = stack.enter_context(
                cm=VirtualMachineBackup(
                    mode=VirtualMachineBackup.Mode.PUSH,
                    name=f"incr{incremental_index}-push-{unique_suffix}",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    pvc_name=push_backup_pvc.name,
                    force_full_backup=False,
                    source=backup_tracker_source,
                )
            )
            wait_for_push_backup_complete(backup=incremental_backup)
            backups.append(incremental_backup)
        yield backups


@pytest.fixture()
def ready_pull_backup_chain(
    request,
    unprivileged_client,
    namespace,
    pull_backup_staging_pvc,
    pull_mode_token_secret,
    vm_with_cbt_label,
    backup_tracker_source,
    unique_suffix,
):
    """
    Sequential pull-mode backup chain: a full backup followed by incremental backups.

    Each backup's export must be deleted before the next backup can reuse the staging PVC, so
    name and status are copied immediately after export becomes ready. Only the last backup in
    the chain still exists when this fixture yields.

    request.param (dict):
        incremental_count: Number of incremental backups to perform after the full backup.
            Use 0 for a full-backup-only chain.

    Side effects:
        Writes new test data to the VM before each incremental backup.

    Returns:
        list[tuple[str, Any]]: (backup name, backup status) for every backup in the chain, in
            order (full backup first, followed by each incremental backup).
    """
    incremental_count = request.param["incremental_count"]
    completed_backups = []
    current_backup = deploy_cbt_pull_backup(
        name=f"full-pull-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_name=pull_mode_token_secret.name,
        pvc_name=pull_backup_staging_pvc.name,
        source=backup_tracker_source,
        force_full_backup=True,
    )
    try:
        wait_for_pull_backup_export_ready(backup=current_backup)
        completed_backups.append((current_backup.name, current_backup.instance.to_dict()["status"]))
        for incremental_index in range(1, incremental_count + 1):
            previous_backup_name = current_backup.name
            current_backup.delete(wait=True)
            wait_for_pull_backup_export_deleted(
                name=previous_backup_name,
                namespace=namespace.name,
                client=unprivileged_client,
            )
            write_file_via_ssh(
                vm=vm_with_cbt_label,
                filename=incremental_test_data_file(index=incremental_index),
                content=incremental_test_data(index=incremental_index),
            )
            current_backup = deploy_cbt_pull_backup(
                name=f"incr{incremental_index}-pull-{unique_suffix}",
                namespace=namespace.name,
                client=unprivileged_client,
                token_secret_name=pull_mode_token_secret.name,
                pvc_name=pull_backup_staging_pvc.name,
                source=backup_tracker_source,
                force_full_backup=False,
            )
            wait_for_pull_backup_export_ready(backup=current_backup)
            completed_backups.append((current_backup.name, current_backup.instance.to_dict()["status"]))
        yield completed_backups
    finally:
        current_backup.clean_up()
