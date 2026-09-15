"""CBT backup fixtures (backup success only)."""

import secrets
from contextlib import ExitStack

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.secret import Secret

from tests.storage.cbt.constants import CBT_ENABLED_LABEL
from tests.storage.cbt.utils import (
    cbt_backup_pvc,
    cbt_backup_tracker,
    cbt_enabled_vm,
    cbt_push_backup,
    cbt_source_ref,
    delete_cbt_pull_backup_and_wait_for_export,
    deploy_cbt_pull_backup,
    incremental_test_data,
    incremental_test_data_file,
    live_migrate_cbt_vm,
    wait_for_pull_backup_export_deleted,
    wait_for_pull_backup_export_ready,
    wait_for_push_backup_complete,
)
from utilities.hco import ResourceEditorValidateHCOReconcile, hco_feature_gates_patch
from utilities.storage import write_file_via_ssh


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
    spec_patch = hco_feature_gates_patch(
        hco_resource=hyperconverged_resource_scope_module,
        enable=["incrementalBackup"],
    )
    spec_patch["spec"]["virtualization"] = {
        "changedBlockTrackingLabelSelectors": {
            "virtualMachineLabelSelector": {"matchLabels": CBT_ENABLED_LABEL},
        }
    }
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: spec_patch,
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=admin_client,
        hco_namespace=hco_namespace.name,
    ):
        yield


@pytest.fixture(scope="module")
def rwx_storage_class_name_scope_module(storage_class_matrix_rwx_matrix__module__):
    """Storage class name from the RWX-only storage class matrix."""
    return [*storage_class_matrix_rwx_matrix__module__][0]


@pytest.fixture()
def vm_with_cbt_label(
    request,
    unprivileged_client,
    namespace,
    cbt_hco_configured,
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
        storage_class_fixture: Optional fixture name that provides the VM disk storage class.
            Defaults to storage_class_name_scope_module.

    Returns:
        VirtualMachine: Running VM with CBT enabled and test data written
    """
    storage_class = request.getfixturevalue(
        argname=request.param.get("storage_class_fixture", "storage_class_name_scope_module")
    )
    with cbt_enabled_vm(
        name=f"{request.param['name']}-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        data_source=rhel9_data_source_scope_session,
        storage_class=storage_class,
        unique_suffix=unique_suffix,
        data_disk_count=request.param.get("data_disk_count", 0),
    ) as vm:
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
    with cbt_backup_tracker(
        namespace=namespace.name,
        client=unprivileged_client,
        vm=vm_with_cbt_label,
    ) as tracker:
        yield tracker


@pytest.fixture()
def backup_tracker_source(backup_tracker_for_vm):
    """
    VirtualMachineBackup.spec.source reference for the VM backup tracker.

    Returns:
        dict: Backup tracker source reference
    """
    return cbt_source_ref(resource=backup_tracker_for_vm)


@pytest.fixture()
def push_backup_pvc(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    storage_class_name_scope_module,
    unique_suffix,
):
    """
    RWO PVC for storing push-mode backup output.

    Returns:
        PersistentVolumeClaim: PVC for push-mode backup storage
    """
    with cbt_backup_pvc(
        name=f"cbt-backup-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        vm=vm_with_cbt_label,
        storage_class=storage_class_name_scope_module,
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
    RWO staging PVC for pull-mode backup export.

    Returns:
        PersistentVolumeClaim: Staging PVC for the pull-mode export
    """
    with cbt_backup_pvc(
        name=f"cbt-staging-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        vm=vm_with_cbt_label,
        storage_class=storage_class_name_scope_module,
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
            cm=cbt_push_backup(
                name=f"full-push-{unique_suffix}",
                namespace=namespace.name,
                client=unprivileged_client,
                pvc_name=push_backup_pvc.name,
                source=backup_tracker_source,
                force_full_backup=True,
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
                cm=cbt_push_backup(
                    name=f"incr{incremental_index}-push-{unique_suffix}",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    pvc_name=push_backup_pvc.name,
                    source=backup_tracker_source,
                    force_full_backup=False,
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
            delete_cbt_pull_backup_and_wait_for_export(backup=current_backup)
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
        final_backup_name = current_backup.name
        current_backup.clean_up()
        wait_for_pull_backup_export_deleted(
            name=final_backup_name,
            namespace=namespace.name,
            client=unprivileged_client,
        )


@pytest.fixture()
def completed_push_backup_after_live_migration(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    push_backup_pvc,
    backup_tracker_source,
    unique_suffix,
    admin_client,
):
    """Full push-mode backup, live-migrate the VM, then one incremental push-mode backup.

    Returns:
        list[VirtualMachineBackup]: The full backup followed by the post-migration incremental backup.
    """
    with ExitStack() as stack:
        full_backup = stack.enter_context(
            cm=cbt_push_backup(
                name=f"full-push-{unique_suffix}",
                namespace=namespace.name,
                client=unprivileged_client,
                pvc_name=push_backup_pvc.name,
                source=backup_tracker_source,
                force_full_backup=True,
            )
        )
        wait_for_push_backup_complete(backup=full_backup)
        live_migrate_cbt_vm(vm=vm_with_cbt_label, client=admin_client)
        write_file_via_ssh(
            vm=vm_with_cbt_label,
            filename=incremental_test_data_file(index=1),
            content=incremental_test_data(index=1),
        )
        incremental_backup = stack.enter_context(
            cm=cbt_push_backup(
                name=f"incr1-push-{unique_suffix}",
                namespace=namespace.name,
                client=unprivileged_client,
                pvc_name=push_backup_pvc.name,
                source=backup_tracker_source,
                force_full_backup=False,
            )
        )
        wait_for_push_backup_complete(backup=incremental_backup)
        yield [full_backup, incremental_backup]


@pytest.fixture()
def ready_pull_backup_after_live_migration(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    pull_backup_staging_pvc,
    pull_mode_token_secret,
    backup_tracker_source,
    unique_suffix,
    admin_client,
):
    """Full pull-mode backup, live-migrate the VM, then one incremental pull-mode backup.

    The full backup's export is deleted before live migration. An active pull-mode
    export holds the VM, so migration cannot complete until the export is gone. Name
    and status of the full backup are copied immediately after export becomes ready.

    Returns:
        list[tuple[str, Any]]: (backup name, backup status) for the full backup and the
            post-migration incremental backup, in that order.
    """
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
        delete_cbt_pull_backup_and_wait_for_export(backup=current_backup)
        current_backup = None
        live_migrate_cbt_vm(vm=vm_with_cbt_label, client=admin_client)
        write_file_via_ssh(
            vm=vm_with_cbt_label,
            filename=incremental_test_data_file(index=1),
            content=incremental_test_data(index=1),
        )
        current_backup = deploy_cbt_pull_backup(
            name=f"incr1-pull-{unique_suffix}",
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
        if current_backup is not None:
            final_backup_name = current_backup.name
            current_backup.clean_up()
            wait_for_pull_backup_export_deleted(
                name=final_backup_name,
                namespace=namespace.name,
                client=unprivileged_client,
            )
