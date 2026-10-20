"""CBT backup and integrity-restore fixtures."""

import logging
import secrets
from contextlib import ExitStack
from typing import Any

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.secret import Secret
from pytest_testconfig import config as py_config

from tests.storage.cbt.constants import (
    CBT_BACKUP_TYPE_FULL,
    CBT_CONCURRENT_VM_COUNT,
    CBT_ENABLED_LABEL,
)
from tests.storage.cbt.restore import (
    CollectedPullBackups,
    ConcurrentCollectedPullBackups,
    cbt_volumes_to_restore,
    collect_cbt_pull_backup,
    pull_export_token,
    restored_cbt_vm_from_pull_backup,
    restored_cbt_vm_from_push_backup,
)
from tests.storage.cbt.utils import (
    cbt_backup_pvc,
    cbt_backup_tracker,
    cbt_backup_wait_timeout,
    cbt_enabled_vm,
    cbt_push_backup,
    cbt_source_ref,
    concurrent_backup_type,
    delete_cbt_pull_backup_and_wait_for_export,
    delete_cbt_pull_backups_and_wait_for_exports,
    deploy_cbt_pull_backup,
    incremental_test_data,
    incremental_test_data_file,
    live_migrate_cbt_vm,
    wait_for_pull_backup_export_deleted,
    wait_for_pull_backup_export_ready,
    wait_for_push_backup_complete,
    write_cbt_guest_file,
    write_incremental_data_for_concurrent_vms,
)
from utilities.hco import ResourceEditorValidateHCOReconcile, hco_feature_gates_patch

LOGGER = logging.getLogger(__name__)


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
    unique_suffix,
):
    """
    VM with CBT enabled, started, and test data written.

    request.param (dict):
        name: VM name prefix.
        data_disk_count: Optional int (default 0). Number of blank data disks (named
            "cbt-datadisk-<index>-<unique_suffix>") to attach before first start (avoiding a
            restart). On Linux VMs, test data is also written to those disks in addition to
            the boot disk. Must be 0 when windows is True.
        storage_class_fixture: Optional fixture name that provides the VM disk storage class.
            Defaults to storage_class_name_scope_module.
        windows: Optional bool (default False). Create a Windows Server 2022 VM with persistent
            vTPM and EFI.
        data_source_fixture: Optional fixture name for the boot-disk DataSource. Defaults to
            rhel9_data_source_scope_session, or windows_validation_os_images_data_source_scope_session
            when windows is True.

    Returns:
        VirtualMachine: Running VM with CBT enabled and test data written
    """
    windows = request.param.get("windows", False)
    storage_class = request.getfixturevalue(
        argname=request.param.get("storage_class_fixture", "storage_class_name_scope_module")
    )
    default_data_source_fixture = (
        "windows_validation_os_images_data_source_scope_session" if windows else "rhel9_data_source_scope_session"
    )
    data_source = request.getfixturevalue(argname=request.param.get("data_source_fixture", default_data_source_fixture))
    with cbt_enabled_vm(
        name=f"{request.param['name']}-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        data_source=data_source,
        storage_class=storage_class,
        unique_suffix=unique_suffix,
        data_disk_count=request.param.get("data_disk_count", 0),
        windows=windows,
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
    unique_suffix,
):
    """
    RWO PVC for storing push-mode backup output on the cluster default storage class.

    Returns:
        PersistentVolumeClaim: PVC for push-mode backup storage
    """
    with cbt_backup_pvc(
        name=f"cbt-backup-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        vm=vm_with_cbt_label,
        storage_class=py_config["default_storage_class"],
    ) as pvc:
        yield pvc


@pytest.fixture()
def pull_backup_staging_pvc(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    unique_suffix,
):
    """
    RWO staging PVC for pull-mode backup export on the cluster default storage class.

    Returns:
        PersistentVolumeClaim: Staging PVC for the pull-mode export
    """
    with cbt_backup_pvc(
        name=f"cbt-staging-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        vm=vm_with_cbt_label,
        storage_class=py_config["default_storage_class"],
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
    backup_wait_timeout = cbt_backup_wait_timeout(vm=vm_with_cbt_label)
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
        wait_for_push_backup_complete(backup=full_backup, wait_timeout=backup_wait_timeout)
        backups.append(full_backup)
        for incremental_index in range(1, incremental_count + 1):
            write_cbt_guest_file(
                vm=vm_with_cbt_label,
                filename=incremental_test_data_file(index=incremental_index, vm=vm_with_cbt_label),
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
            wait_for_push_backup_complete(backup=incremental_backup, wait_timeout=backup_wait_timeout)
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
    Sequential pull-mode backup chain collected to client storage.

    Each backup's export must be deleted before the next backup can reuse the staging PVC.
    The export is downloaded onto the client PVC first. Name and status are copied immediately
    after export becomes ready. Every export is deleted before this fixture yields so the
    source VM can be removed for restore. The client PVC remains until the fixture exits.

    request.param (dict):
        incremental_count: Number of incremental backups to perform after the full backup.
            Use 0 for a full-backup-only chain.

    Side effects:
        Writes new test data to the VM before each incremental backup and downloads every
        ready export onto the client PVC.

    Returns:
        CollectedPullBackups: Captured backup name/status pairs, oldest first, and the client
            PVC name that holds the raw snapshots.
    """
    incremental_count = request.param["incremental_count"]
    backup_wait_timeout = cbt_backup_wait_timeout(vm=vm_with_cbt_label)
    volume_names = cbt_volumes_to_restore(vm=vm_with_cbt_label)
    with cbt_backup_pvc(
        name=f"cbt-pull-client-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        vm=vm_with_cbt_label,
        storage_class=py_config["default_storage_class"],
        backup_copies=1 + incremental_count,
    ) as client_pvc:
        export_token = pull_export_token(secret=pull_mode_token_secret)
        completed_backups: list[tuple[str, dict[str, Any]]] = []
        current_backup = deploy_cbt_pull_backup(
            name=f"full-pull-{unique_suffix}",
            namespace=namespace.name,
            client=unprivileged_client,
            token_secret_name=pull_mode_token_secret.name,
            pvc_name=pull_backup_staging_pvc.name,
            source=backup_tracker_source,
            force_full_backup=True,
        )
        backup_needs_cleanup = True
        try:
            wait_for_pull_backup_export_ready(backup=current_backup, wait_timeout=backup_wait_timeout)
            collect_cbt_pull_backup(
                backup=current_backup,
                vm=vm_with_cbt_label,
                export_token=export_token,
                client_backup_pvc_name=client_pvc.name,
                volume_names=volume_names,
                checkpoint_index=0,
            )
            completed_backups.append((current_backup.name, current_backup.instance.to_dict()["status"]))
            for incremental_index in range(1, incremental_count + 1):
                delete_cbt_pull_backup_and_wait_for_export(backup=current_backup)
                backup_needs_cleanup = False
                write_cbt_guest_file(
                    vm=vm_with_cbt_label,
                    filename=incremental_test_data_file(index=incremental_index, vm=vm_with_cbt_label),
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
                backup_needs_cleanup = True
                wait_for_pull_backup_export_ready(backup=current_backup, wait_timeout=backup_wait_timeout)
                collect_cbt_pull_backup(
                    backup=current_backup,
                    vm=vm_with_cbt_label,
                    export_token=export_token,
                    client_backup_pvc_name=client_pvc.name,
                    volume_names=volume_names,
                    checkpoint_index=incremental_index,
                )
                completed_backups.append((current_backup.name, current_backup.instance.to_dict()["status"]))
            delete_cbt_pull_backup_and_wait_for_export(backup=current_backup)
            backup_needs_cleanup = False
            yield CollectedPullBackups(backups=completed_backups, client_pvc_name=client_pvc.name)
        finally:
            if backup_needs_cleanup:
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
    backup_wait_timeout = cbt_backup_wait_timeout(vm=vm_with_cbt_label)
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
        wait_for_push_backup_complete(backup=full_backup, wait_timeout=backup_wait_timeout)
        live_migrate_cbt_vm(vm=vm_with_cbt_label, client=admin_client)
        write_cbt_guest_file(
            vm=vm_with_cbt_label,
            filename=incremental_test_data_file(index=1, vm=vm_with_cbt_label),
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
        wait_for_push_backup_complete(backup=incremental_backup, wait_timeout=backup_wait_timeout)
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

    Each export is downloaded to the client PVC before it is deleted. The full backup's
    export is deleted before live migration. An active pull-mode export holds the VM, so
    migration cannot complete until the export is gone. Name and status of each backup
    are copied immediately after export becomes ready.

    Returns:
        CollectedPullBackups: Captured full and incremental backup status, in that order,
            and the client PVC that holds both raw snapshots.
    """
    backup_wait_timeout = cbt_backup_wait_timeout(vm=vm_with_cbt_label)
    volume_names = cbt_volumes_to_restore(vm=vm_with_cbt_label)
    with cbt_backup_pvc(
        name=f"cbt-pull-client-{unique_suffix}",
        namespace=namespace.name,
        client=unprivileged_client,
        vm=vm_with_cbt_label,
        storage_class=py_config["default_storage_class"],
        backup_copies=2,
    ) as client_pvc:
        export_token = pull_export_token(secret=pull_mode_token_secret)
        completed_backups: list[tuple[str, dict[str, Any]]] = []
        current_backup = deploy_cbt_pull_backup(
            name=f"full-pull-{unique_suffix}",
            namespace=namespace.name,
            client=unprivileged_client,
            token_secret_name=pull_mode_token_secret.name,
            pvc_name=pull_backup_staging_pvc.name,
            source=backup_tracker_source,
            force_full_backup=True,
        )
        backup_needs_cleanup = True
        try:
            wait_for_pull_backup_export_ready(backup=current_backup, wait_timeout=backup_wait_timeout)
            collect_cbt_pull_backup(
                backup=current_backup,
                vm=vm_with_cbt_label,
                export_token=export_token,
                client_backup_pvc_name=client_pvc.name,
                volume_names=volume_names,
                checkpoint_index=0,
            )
            completed_backups.append((current_backup.name, current_backup.instance.to_dict()["status"]))
            delete_cbt_pull_backup_and_wait_for_export(backup=current_backup)
            backup_needs_cleanup = False
            live_migrate_cbt_vm(vm=vm_with_cbt_label, client=admin_client)
            write_cbt_guest_file(
                vm=vm_with_cbt_label,
                filename=incremental_test_data_file(index=1, vm=vm_with_cbt_label),
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
            backup_needs_cleanup = True
            wait_for_pull_backup_export_ready(backup=current_backup, wait_timeout=backup_wait_timeout)
            collect_cbt_pull_backup(
                backup=current_backup,
                vm=vm_with_cbt_label,
                export_token=export_token,
                client_backup_pvc_name=client_pvc.name,
                volume_names=volume_names,
                checkpoint_index=1,
            )
            completed_backups.append((current_backup.name, current_backup.instance.to_dict()["status"]))
            delete_cbt_pull_backup_and_wait_for_export(backup=current_backup)
            backup_needs_cleanup = False
            yield CollectedPullBackups(backups=completed_backups, client_pvc_name=client_pvc.name)
        finally:
            if backup_needs_cleanup:
                final_backup_name = current_backup.name
                current_backup.clean_up()
                wait_for_pull_backup_export_deleted(
                    name=final_backup_name,
                    namespace=namespace.name,
                    client=unprivileged_client,
                )


@pytest.fixture()
def concurrent_cbt_vms(
    unprivileged_client,
    namespace,
    cbt_hco_configured,
    rhel9_data_source_scope_session,
    unique_suffix,
    storage_class_name_scope_module,
):
    """Running CBT-enabled VMs with test data written to each boot disk.

    Returns:
        list[VirtualMachineForTests]: Running VMs, in index order. The first
            CBT_CONCURRENT_INCREMENTAL_COUNT VMs are the ones that take an incremental backup.
    """
    with ExitStack() as stack:
        vms = []
        for vm_index in range(1, CBT_CONCURRENT_VM_COUNT + 1):
            LOGGER.info(f"Creating concurrent CBT VM {vm_index} of {CBT_CONCURRENT_VM_COUNT}")
            vm = stack.enter_context(
                cm=cbt_enabled_vm(
                    name=f"cbt-conc-{vm_index}-{unique_suffix}",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    data_source=rhel9_data_source_scope_session,
                    storage_class=storage_class_name_scope_module,
                    unique_suffix=unique_suffix,
                )
            )
            vms.append(vm)
        yield vms


@pytest.fixture()
def concurrent_cbt_backup_trackers(
    unprivileged_client,
    namespace,
    concurrent_cbt_vms,
):
    """Backup tracker for each concurrent CBT VM, in the same order as the VMs.

    Returns:
        list[VirtualMachineBackupTracker]: Tracker for each VM.
    """
    with ExitStack() as stack:
        trackers = []
        for vm in concurrent_cbt_vms:
            trackers.append(
                stack.enter_context(
                    cm=cbt_backup_tracker(
                        namespace=namespace.name,
                        client=unprivileged_client,
                        vm=vm,
                    )
                )
            )
        yield trackers


@pytest.fixture()
def concurrent_push_backup_pvcs(
    unprivileged_client,
    namespace,
    concurrent_cbt_vms,
    unique_suffix,
):
    """Push-mode backup PVC for each concurrent CBT VM, in the same order as the VMs.

    Returns:
        list[PersistentVolumeClaim]: Backup PVC for each VM.
    """
    with ExitStack() as stack:
        pvcs = []
        for vm_index, vm in enumerate(concurrent_cbt_vms, start=1):
            pvcs.append(
                stack.enter_context(
                    cm=cbt_backup_pvc(
                        name=f"cbt-backup-{vm_index}-{unique_suffix}",
                        namespace=namespace.name,
                        client=unprivileged_client,
                        vm=vm,
                        storage_class=py_config["default_storage_class"],
                    )
                )
            )
        yield pvcs


@pytest.fixture()
def concurrent_pull_staging_pvcs(
    unprivileged_client,
    namespace,
    concurrent_cbt_vms,
    unique_suffix,
):
    """Pull-mode staging PVC for each concurrent CBT VM, in the same order as the VMs.

    Returns:
        list[PersistentVolumeClaim]: Staging PVC for each VM.
    """
    with ExitStack() as stack:
        pvcs = []
        for vm_index, vm in enumerate(concurrent_cbt_vms, start=1):
            pvcs.append(
                stack.enter_context(
                    cm=cbt_backup_pvc(
                        name=f"cbt-staging-{vm_index}-{unique_suffix}",
                        namespace=namespace.name,
                        client=unprivileged_client,
                        vm=vm,
                        storage_class=py_config["default_storage_class"],
                    )
                )
            )
        yield pvcs


@pytest.fixture()
def concurrent_push_backup_chains(
    unprivileged_client,
    namespace,
    concurrent_cbt_vms,
    concurrent_cbt_backup_trackers,
    concurrent_push_backup_pvcs,
    unique_suffix,
):
    """Push-mode backup chain for each concurrent VM.

    VMs whose concurrent backup is incremental first get a completed full backup and new
    guest data. Every concurrent backup is created before any of them is waited on.

    Returns:
        list[list[VirtualMachineBackup]]: One chain per VM, oldest backup first. Incremental
            VMs contain the preparatory full backup and the concurrent incremental backup.
            Full VMs contain only the concurrent full backup.
    """
    with ExitStack() as stack:
        backup_chains: list[list[Any]] = [[] for _ in concurrent_cbt_vms]
        preparatory_backups = []
        for backup_index, vm in enumerate(concurrent_cbt_vms):
            if concurrent_backup_type(backup_index=backup_index) == CBT_BACKUP_TYPE_FULL:
                continue
            LOGGER.info(f"Starting preparatory full push backup for VM {vm.name}")
            preparatory_backup = stack.enter_context(
                cm=cbt_push_backup(
                    name=f"prep-full-push-{backup_index + 1}-{unique_suffix}",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    pvc_name=concurrent_push_backup_pvcs[backup_index].name,
                    source=cbt_source_ref(resource=concurrent_cbt_backup_trackers[backup_index]),
                    force_full_backup=True,
                )
            )
            backup_chains[backup_index].append(preparatory_backup)
            preparatory_backups.append(preparatory_backup)
        for preparatory_backup in preparatory_backups:
            wait_for_push_backup_complete(backup=preparatory_backup)
        write_incremental_data_for_concurrent_vms(vms=concurrent_cbt_vms)
        concurrent_backups = []
        for backup_index, vm in enumerate(concurrent_cbt_vms):
            force_full_backup = concurrent_backup_type(backup_index=backup_index) == CBT_BACKUP_TYPE_FULL
            backup_name_prefix = "full" if force_full_backup else "incr"
            LOGGER.info(f"Starting concurrent push backup {backup_name_prefix} for VM {vm.name}")
            concurrent_backup = stack.enter_context(
                cm=cbt_push_backup(
                    name=f"{backup_name_prefix}-push-{backup_index + 1}-{unique_suffix}",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    pvc_name=concurrent_push_backup_pvcs[backup_index].name,
                    source=cbt_source_ref(resource=concurrent_cbt_backup_trackers[backup_index]),
                    force_full_backup=force_full_backup,
                )
            )
            backup_chains[backup_index].append(concurrent_backup)
            concurrent_backups.append(concurrent_backup)
        LOGGER.info(f"Waiting for {len(concurrent_backups)} simultaneous push-mode backups")
        for concurrent_backup in concurrent_backups:
            wait_for_push_backup_complete(backup=concurrent_backup)
        yield backup_chains


@pytest.fixture()
def completed_concurrent_push_backups(concurrent_push_backup_chains):
    """The simultaneous push-mode backup from each concurrent VM chain.

    Returns:
        list[VirtualMachineBackup]: Concurrent-wave backups, in the same order as the VMs.
    """
    return [backup_chain[-1] for backup_chain in concurrent_push_backup_chains]


@pytest.fixture()
def ready_concurrent_pull_backups(
    unprivileged_client,
    namespace,
    concurrent_cbt_vms,
    concurrent_cbt_backup_trackers,
    concurrent_pull_staging_pvcs,
    pull_mode_token_secret,
    unique_suffix,
):
    """Simultaneous pull-mode backups across all concurrent VMs, collected to client PVCs.

    VMs whose concurrent backup is incremental first get a completed full backup. That export
    is downloaded and deleted, then new guest data is written. Every concurrent backup is
    created before any of them is waited on, then downloaded onto that VM's client PVC.

    Returns:
        ConcurrentCollectedPullBackups: Captured concurrent-wave backup status, in VM order,
            and one client PVC name per VM. Exports are deleted before the fixture yields.
    """
    export_token = pull_export_token(secret=pull_mode_token_secret)
    deployed_backups = []
    with ExitStack() as stack:
        client_pvcs = []
        for vm_index, vm in enumerate(concurrent_cbt_vms, start=1):
            client_pvcs.append(
                stack.enter_context(
                    cm=cbt_backup_pvc(
                        name=f"cbt-pull-client-{vm_index}-{unique_suffix}",
                        namespace=namespace.name,
                        client=unprivileged_client,
                        vm=vm,
                        storage_class=py_config["default_storage_class"],
                        backup_copies=2,
                    )
                )
            )
        try:
            preparatory_backups = []
            for backup_index, vm in enumerate(concurrent_cbt_vms):
                if concurrent_backup_type(backup_index=backup_index) == CBT_BACKUP_TYPE_FULL:
                    continue
                LOGGER.info(f"Starting preparatory full pull backup for VM {vm.name}")
                preparatory_backup = deploy_cbt_pull_backup(
                    name=f"prep-full-pull-{backup_index + 1}-{unique_suffix}",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    token_secret_name=pull_mode_token_secret.name,
                    pvc_name=concurrent_pull_staging_pvcs[backup_index].name,
                    source=cbt_source_ref(resource=concurrent_cbt_backup_trackers[backup_index]),
                    force_full_backup=True,
                )
                preparatory_backups.append((backup_index, preparatory_backup))
                deployed_backups.append(preparatory_backup)
            for backup_index, preparatory_backup in preparatory_backups:
                LOGGER.info(f"Waiting for preparatory pull backup of VM {concurrent_cbt_vms[backup_index].name}")
                wait_for_pull_backup_export_ready(backup=preparatory_backup)
                collect_cbt_pull_backup(
                    backup=preparatory_backup,
                    vm=concurrent_cbt_vms[backup_index],
                    export_token=export_token,
                    client_backup_pvc_name=client_pvcs[backup_index].name,
                    volume_names=cbt_volumes_to_restore(vm=concurrent_cbt_vms[backup_index]),
                    checkpoint_index=0,
                )
                delete_cbt_pull_backup_and_wait_for_export(backup=preparatory_backup)
                deployed_backups.remove(preparatory_backup)
            write_incremental_data_for_concurrent_vms(vms=concurrent_cbt_vms)
            concurrent_backups = []
            for backup_index, vm in enumerate(concurrent_cbt_vms):
                force_full_backup = concurrent_backup_type(backup_index=backup_index) == CBT_BACKUP_TYPE_FULL
                backup_name_prefix = "full" if force_full_backup else "incr"
                LOGGER.info(f"Starting concurrent pull backup {backup_name_prefix} for VM {vm.name}")
                concurrent_backup = deploy_cbt_pull_backup(
                    name=f"{backup_name_prefix}-pull-{backup_index + 1}-{unique_suffix}",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    token_secret_name=pull_mode_token_secret.name,
                    pvc_name=concurrent_pull_staging_pvcs[backup_index].name,
                    source=cbt_source_ref(resource=concurrent_cbt_backup_trackers[backup_index]),
                    force_full_backup=force_full_backup,
                )
                concurrent_backups.append(concurrent_backup)
                deployed_backups.append(concurrent_backup)
            LOGGER.info(f"Waiting for {len(concurrent_backups)} simultaneous pull-mode backups")
            for concurrent_backup in concurrent_backups:
                wait_for_pull_backup_export_ready(backup=concurrent_backup)
            captured_backups: list[tuple[str, dict[str, Any]]] = []
            for backup_index, concurrent_backup in enumerate(concurrent_backups):
                checkpoint_index = 0 if concurrent_backup_type(backup_index=backup_index) == CBT_BACKUP_TYPE_FULL else 1
                collect_cbt_pull_backup(
                    backup=concurrent_backup,
                    vm=concurrent_cbt_vms[backup_index],
                    export_token=export_token,
                    client_backup_pvc_name=client_pvcs[backup_index].name,
                    volume_names=cbt_volumes_to_restore(vm=concurrent_cbt_vms[backup_index]),
                    checkpoint_index=checkpoint_index,
                )
                captured_backups.append((concurrent_backup.name, concurrent_backup.instance.to_dict()["status"]))
            delete_cbt_pull_backups_and_wait_for_exports(
                backups=deployed_backups,
                namespace=namespace.name,
                client=unprivileged_client,
            )
            deployed_backups.clear()
            yield ConcurrentCollectedPullBackups(
                backups=captured_backups,
                client_pvc_names=[client_pvc.name for client_pvc in client_pvcs],
            )
        finally:
            delete_cbt_pull_backups_and_wait_for_exports(
                backups=deployed_backups,
                namespace=namespace.name,
                client=unprivileged_client,
            )


@pytest.fixture()
def restored_vm_from_push_chain(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    completed_push_backup_chain,
    push_backup_pvc,
):
    """Running VM restored from the completed push-mode backup chain.

    Returns:
        VirtualMachineForTests: Restored VM with the original VM name.
    """
    with restored_cbt_vm_from_push_backup(
        vm=vm_with_cbt_label,
        backups=completed_push_backup_chain,
        backup_pvc_name=push_backup_pvc.name,
        namespace=namespace.name,
        client=unprivileged_client,
    ) as restored_vm:
        yield restored_vm


@pytest.fixture()
def restored_vm_from_pull_chain(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    ready_pull_backup_chain,
):
    """Running VM restored from the collected pull-mode backup chain.

    Returns:
        VirtualMachineForTests: Restored VM with the original VM name.
    """
    with restored_cbt_vm_from_pull_backup(
        vm=vm_with_cbt_label,
        client_backup_pvc_name=ready_pull_backup_chain.client_pvc_name,
        namespace=namespace.name,
        client=unprivileged_client,
    ) as restored_vm:
        yield restored_vm


@pytest.fixture()
def restored_vm_from_push_after_live_migration(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    completed_push_backup_after_live_migration,
    push_backup_pvc,
):
    """Running VM restored from the post-migration push-mode backup chain.

    Returns:
        VirtualMachineForTests: Restored VM with the original VM name.
    """
    with restored_cbt_vm_from_push_backup(
        vm=vm_with_cbt_label,
        backups=completed_push_backup_after_live_migration,
        backup_pvc_name=push_backup_pvc.name,
        namespace=namespace.name,
        client=unprivileged_client,
    ) as restored_vm:
        yield restored_vm


@pytest.fixture()
def restored_vm_from_pull_after_live_migration(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    ready_pull_backup_after_live_migration,
):
    """Running VM restored from the post-migration pull-mode backup chain.

    Returns:
        VirtualMachineForTests: Restored VM with the original VM name.
    """
    with restored_cbt_vm_from_pull_backup(
        vm=vm_with_cbt_label,
        client_backup_pvc_name=ready_pull_backup_after_live_migration.client_pvc_name,
        namespace=namespace.name,
        client=unprivileged_client,
    ) as restored_vm:
        yield restored_vm


@pytest.fixture()
def restored_vms_from_concurrent_push(
    unprivileged_client,
    namespace,
    concurrent_cbt_vms,
    concurrent_push_backup_chains,
    concurrent_push_backup_pvcs,
):
    """Running VMs restored from each concurrent push-mode backup chain.

    Returns:
        list[VirtualMachineForTests]: Restored VMs, in the same order as the source VMs.
    """
    with ExitStack() as stack:
        restored_vms = []
        for vm, backup_chain, backup_pvc in zip(
            concurrent_cbt_vms,
            concurrent_push_backup_chains,
            concurrent_push_backup_pvcs,
            strict=True,
        ):
            restored_vms.append(
                stack.enter_context(
                    cm=restored_cbt_vm_from_push_backup(
                        vm=vm,
                        backups=backup_chain,
                        backup_pvc_name=backup_pvc.name,
                        namespace=namespace.name,
                        client=unprivileged_client,
                    )
                )
            )
        yield restored_vms


@pytest.fixture()
def restored_vms_from_concurrent_pull(
    unprivileged_client,
    namespace,
    concurrent_cbt_vms,
    ready_concurrent_pull_backups,
):
    """Running VMs restored from each concurrent pull-mode client backup.

    Returns:
        list[VirtualMachineForTests]: Restored VMs, in the same order as the source VMs.
    """
    with ExitStack() as stack:
        restored_vms = []
        for vm, client_pvc_name in zip(
            concurrent_cbt_vms,
            ready_concurrent_pull_backups.client_pvc_names,
            strict=True,
        ):
            restored_vms.append(
                stack.enter_context(
                    cm=restored_cbt_vm_from_pull_backup(
                        vm=vm,
                        client_backup_pvc_name=client_pvc_name,
                        namespace=namespace.name,
                        client=unprivileged_client,
                    )
                )
            )
        yield restored_vms
