"""
CBT (Changed Block Tracking) test fixtures.

Fixtures for setting up VMs, backups, and restores for CBT testing.
"""

import base64
import secrets

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.secret import Secret
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine import VirtualMachine
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
    cbt_storage_class_suffix,
    create_and_collect_pull_mode_backup,
    restore_and_start_vm_from_pull_client_backup,
)
from utilities.constants.images import OS_FLAVOR_RHEL
from utilities.constants.instance_types import RHEL9_PREFERENCE, U1_SMALL
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
        name=f"{request.param['name']}-{cbt_storage_class_suffix(storage_class_name=storage_class_name_scope_module)}",
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
def vm_boot_disk_size(vm_with_cbt_label):
    """
    Boot disk size request from the under-test VM data volume template.

    Returns:
        str: Boot disk storage request (e.g. 30Gi)
    """
    return vm_with_cbt_label.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"]


@pytest.fixture(scope="module")
def vm_boot_pvc_spec(admin_client, storage_class_name_scope_module):
    """
    Default volume mode and access mode for the test storage class.

    Reads the first claimPropertySet from the CDI StorageProfile, which reflects
    what the cluster applies when a PVC is created without explicit volumeMode or
    accessModes (i.e. our data volume templates).

    Returns:
        dict: PVC spec with 'volume_mode' (str) and 'access_mode' (str)
    """
    profile = StorageProfile(
        name=storage_class_name_scope_module,
        client=admin_client,
    )
    return {
        "volume_mode": profile.first_claim_property_set_volume_mode(),
        "access_mode": profile.first_claim_property_set_access_modes()[0],
    }


# Pull mode fixtures


@pytest.fixture()
def pull_backup_staging_pvc(
    unprivileged_client,
    namespace,
    vm_boot_disk_size,
    storage_class_name_scope_module,
):
    """
    Controller-side staging PVC for pull-mode backup export.

    The backup controller mounts this PVC to stage the exported snapshot during
    the backup export window. It is ephemeral: deleted together with the
    VirtualMachineBackup CR once the client has pulled the data.

    Returns:
        PersistentVolumeClaim: Staging PVC for the pull-mode export
    """
    with PersistentVolumeClaim(
        name=f"cbt-staging-{cbt_storage_class_suffix(storage_class_name=storage_class_name_scope_module)}",
        namespace=namespace.name,
        client=unprivileged_client,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=cbt_pvc_size_with_headroom(source_disk_size=vm_boot_disk_size),
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

    Pull-mode backups require a user-generated token in tokenSecretRef; the export
    endpoints authorize external clients using this secret value.

    Returns:
        Secret: Pull-mode token secret
    """
    with Secret(
        name=f"cbt-pull-token-{cbt_storage_class_suffix(storage_class_name=storage_class_name_scope_module)}",
        namespace=namespace.name,
        client=unprivileged_client,
        string_data={"token": secrets.token_urlsafe(nbytes=16)},
    ) as secret:
        yield secret


@pytest.fixture()
def pull_client_backup_pvc(
    unprivileged_client,
    namespace,
    vm_boot_disk_size,
    storage_class_name_scope_module,
):
    """
    PVC simulating off-site client storage for pull-mode backup data.

    Sized for a full raw snapshot plus an incremental snapshot. Pull-mode
    incremental collection seeds the new checkpoint by copying the previous
    raw file before downloading changed blocks.

    Returns:
        PersistentVolumeClaim: Client-side backup storage PVC
    """
    with PersistentVolumeClaim(
        name=f"cbt-pull-client-{cbt_storage_class_suffix(storage_class_name=storage_class_name_scope_module)}",
        namespace=namespace.name,
        client=unprivileged_client,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size=cbt_pvc_size_with_headroom(source_disk_size=vm_boot_disk_size, backup_copies=2),
        storage_class=storage_class_name_scope_module,
        volume_mode=PersistentVolumeClaim.VolumeMode.FILE,
    ) as pvc:
        yield pvc


@pytest.fixture()
def collected_full_backup_pull_mode(
    unprivileged_client,
    namespace,
    pull_backup_staging_pvc,
    pull_mode_token_secret,
    pull_client_backup_pvc,
    vm_boot_disk_size,
    backup_tracker_source,
    storage_class_name_scope_module,
):
    """
    Full pull-mode backup collected to client storage with the backup CR deleted.

    Returns:
        str: Name of the client PVC containing offline pull backup data
    """
    create_and_collect_pull_mode_backup(
        name=f"full-pull-{cbt_storage_class_suffix(storage_class_name=storage_class_name_scope_module)}",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_name=pull_mode_token_secret.name,
        export_token=base64.b64decode(pull_mode_token_secret.instance.data["token"]).decode("utf-8"),
        staging_pvc_name=pull_backup_staging_pvc.name,
        client_backup_pvc_name=pull_client_backup_pvc.name,
        backup_tracker_source=backup_tracker_source,
        force_full_backup=True,
        boot_disk_size=vm_boot_disk_size,
    )
    yield pull_client_backup_pvc.name


@pytest.fixture()
def restored_vm_from_full_backup_pull_mode(
    unprivileged_client,
    namespace,
    collected_full_backup_pull_mode,
    vm_with_cbt_label,
    vm_boot_disk_size,
    vm_boot_pvc_spec,
    storage_class_name_scope_module,
):
    """
    VM restored from collected pull-mode client storage and started with the original VM name.

    Returns:
        VirtualMachineForTests: Running restored VM
    """
    yield from restore_and_start_vm_from_pull_client_backup(
        vm=vm_with_cbt_label,
        client_backup_pvc_name=collected_full_backup_pull_mode,
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
        size=vm_boot_disk_size,
        **vm_boot_pvc_spec,
    )


@pytest.fixture()
def collected_incremental_backup_pull_mode(
    unprivileged_client,
    namespace,
    pull_backup_staging_pvc,
    pull_mode_token_secret,
    pull_client_backup_pvc,
    vm_with_cbt_label,
    vm_boot_disk_size,
    collected_full_backup_pull_mode,
    backup_tracker_source,
    storage_class_name_scope_module,
):
    """
    Incremental pull-mode backup collected to client storage with the backup CR deleted.

    Returns:
        str: Name of the client PVC containing offline full and incremental pull backup data
    """
    write_file_via_ssh(
        vm=vm_with_cbt_label,
        filename=CBT_INCREMENTAL_TEST_DATA_FILE,
        content=CBT_INCREMENTAL_TEST_DATA,
    )
    create_and_collect_pull_mode_backup(
        name=f"incr-pull-{cbt_storage_class_suffix(storage_class_name=storage_class_name_scope_module)}",
        namespace=namespace.name,
        client=unprivileged_client,
        token_secret_name=pull_mode_token_secret.name,
        export_token=base64.b64decode(pull_mode_token_secret.instance.data["token"]).decode("utf-8"),
        staging_pvc_name=pull_backup_staging_pvc.name,
        client_backup_pvc_name=pull_client_backup_pvc.name,
        backup_tracker_source=backup_tracker_source,
        force_full_backup=False,
        boot_disk_size=vm_boot_disk_size,
    )
    yield collected_full_backup_pull_mode


@pytest.fixture()
def restored_vm_from_incremental_backup_pull_mode(
    unprivileged_client,
    namespace,
    collected_incremental_backup_pull_mode,
    vm_with_cbt_label,
    vm_boot_disk_size,
    vm_boot_pvc_spec,
    storage_class_name_scope_module,
):
    """
    VM restored from collected incremental pull-mode client storage and started with the original VM name.

    Returns:
        VirtualMachineForTests: Running restored VM
    """
    yield from restore_and_start_vm_from_pull_client_backup(
        vm=vm_with_cbt_label,
        client_backup_pvc_name=collected_incremental_backup_pull_mode,
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
        size=vm_boot_disk_size,
        **vm_boot_pvc_spec,
    )
