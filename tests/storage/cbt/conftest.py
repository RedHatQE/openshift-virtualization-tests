"""CBT backup fixtures (backup success only)."""

import secrets

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.secret import Secret
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_backup import VirtualMachineBackup
from ocp_resources.virtual_machine_backup_tracker import VirtualMachineBackupTracker
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from tests.storage.cbt.utils import (
    CBT_BOOT_DISK_TEST_DATA_FILE,
    CBT_ENABLED_LABEL,
    CBT_INCREMENTAL_TEST_DATA,
    CBT_INCREMENTAL_TEST_DATA_FILE,
    CBT_TEST_DATA,
    cbt_pvc_size_with_headroom,
    cbt_resource_id,
    wait_for_pull_backup_export_deleted,
    wait_for_vm_cbt_enabled,
)
from utilities.constants.images import OS_FLAVOR_RHEL
from utilities.constants.instance_types import RHEL9_PREFERENCE, U1_SMALL
from utilities.constants.timeouts import TIMEOUT_5SEC, TIMEOUT_10MIN
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import (
    data_volume_template_with_source_ref_dict,
    write_file_via_ssh,
)
from utilities.virt import VirtualMachineForTests, running_vm


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
):
    """
    VM with CBT enabled, started, and test data written.

    Returns:
        VirtualMachine: Running VM with CBT enabled and test data written
    """
    with VirtualMachineForTests(
        name=f"{request.param['name']}-{cbt_resource_id(name=storage_class_name_scope_module)}",
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
        wait_for_vm_cbt_enabled(vm=vm)
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
def pull_backup_staging_pvc(
    unprivileged_client,
    namespace,
    vm_with_cbt_label,
    storage_class_name_scope_module,
):
    """
    Controller-side staging PVC for pull-mode backup export.

    Returns:
        PersistentVolumeClaim: Staging PVC for the pull-mode export
    """
    boot_disk_size = vm_with_cbt_label.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"]
    with PersistentVolumeClaim(
        name=f"cbt-staging-{cbt_resource_id(name=storage_class_name_scope_module)}",
        namespace=namespace.name,
        client=unprivileged_client,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=cbt_pvc_size_with_headroom(source_disk_size=boot_disk_size),
        storage_class=storage_class_name_scope_module,
        volume_mode=PersistentVolumeClaim.VolumeMode.FILE,
    ) as pvc:
        yield pvc


@pytest.fixture()
def pull_mode_token_secret(
    unprivileged_client,
    namespace,
    storage_class_name_scope_module,
):
    """
    User-provided export token secret for pull-mode backup authentication.

    Returns:
        Secret: Pull-mode token secret
    """
    with Secret(
        name=f"cbt-pull-token-{cbt_resource_id(name=storage_class_name_scope_module)}",
        namespace=namespace.name,
        client=unprivileged_client,
        string_data={"token": secrets.token_urlsafe(nbytes=16)},
    ) as secret:
        yield secret


@pytest.fixture()
def ready_full_backup_pull_mode(
    unprivileged_client,
    namespace,
    pull_backup_staging_pvc,
    pull_mode_token_secret,
    backup_tracker_source,
    storage_class_name_scope_module,
):
    """
    Full pull-mode backup after export is ready (no collect).

    Returns:
        VirtualMachineBackup: Pull backup with export endpoints ready
    """
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name=f"full-pull-{cbt_resource_id(name=storage_class_name_scope_module)}",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret.name,
        pvc_name=pull_backup_staging_pvc.name,
        force_full_backup=True,
        source=backup_tracker_source,
    ) as backup:
        # Pull readiness is Progressing=True with reason ExportReady (there is no ExportReady condition type).
        backup.wait_for_condition(
            condition="Progressing",
            status=VirtualMachineBackup.Condition.Status.TRUE,
            reason="ExportReady",
            timeout=TIMEOUT_10MIN,
            sleep_time=TIMEOUT_5SEC,
        )
        yield backup


@pytest.fixture()
def ready_incremental_backup_pull_mode(
    unprivileged_client,
    namespace,
    pull_backup_staging_pvc,
    pull_mode_token_secret,
    vm_with_cbt_label,
    ready_full_backup_pull_mode,
    backup_tracker_source,
    storage_class_name_scope_module,
):
    """
    Incremental pull-mode backup after export is ready (no collect).

    Deletes the prior full pull backup so the staging PVC and export can be reused.

    Returns:
        VirtualMachineBackup: Incremental pull backup with export endpoints ready
    """
    full_backup_name = ready_full_backup_pull_mode.name
    ready_full_backup_pull_mode.delete(wait=True)
    ready_full_backup_pull_mode.teardown = False
    wait_for_pull_backup_export_deleted(
        name=full_backup_name,
        namespace=namespace.name,
        client=unprivileged_client,
    )
    write_file_via_ssh(
        vm=vm_with_cbt_label,
        filename=CBT_INCREMENTAL_TEST_DATA_FILE,
        content=CBT_INCREMENTAL_TEST_DATA,
    )
    with VirtualMachineBackup(
        mode=VirtualMachineBackup.Mode.PULL,
        name=f"incr-pull-{cbt_resource_id(name=storage_class_name_scope_module)}",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_ref=pull_mode_token_secret.name,
        pvc_name=pull_backup_staging_pvc.name,
        force_full_backup=False,
        source=backup_tracker_source,
    ) as backup:
        # Pull readiness is Progressing=True with reason ExportReady (there is no ExportReady condition type).
        backup.wait_for_condition(
            condition="Progressing",
            status=VirtualMachineBackup.Condition.Status.TRUE,
            reason="ExportReady",
            timeout=TIMEOUT_10MIN,
            sleep_time=TIMEOUT_5SEC,
        )
        yield backup
