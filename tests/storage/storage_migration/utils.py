import shlex

import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.multi_namespace_virtual_machine_storage_migration import MultiNamespaceVirtualMachineStorageMigration
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.storage.storage_migration.constants import (
    CONTENT,
    FILE_BEFORE_STORAGE_MIGRATION,
    HOTPLUGGED_DEVICES,
    MOUNT_HOTPLUGGED_DEVICE_PATHS,
    STORAGE_MIGRATION_IN_PROGRESS_PHASE,
)
from tests.storage.utils import check_file_in_vm
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.instance_types import U1_SMALL
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5SEC, TIMEOUT_10MIN, TIMEOUT_10SEC
from utilities.exceptions import StorageMigrationError
from utilities.jira import is_jira_open
from utilities.storage import (
    data_volume_template_with_source_ref_dict,
    wait_for_vm_volume_ready,
)
from utilities.virt import VirtualMachineForTests, get_vm_boot_time, running_vm


def create_fedora_vm_with_instance_type(
    unprivileged_client,
    namespace_name: str,
    data_source: DataSource,
    source_storage_class: str,
    cpu_for_migration: str,
    vm_name: str,
):
    """Create a running fedora VM with an instance type.

    Args:
        unprivileged_client: Kubernetes client for VM creation.
        namespace_name: Namespace where the VM will be created.
        data_source: DataSource for the VM's DataVolume source.
        source_storage_class: Storage class for the VM's DataVolume.
        cpu_for_migration: CPU model for migration compatibility.
        vm_name: Name for the VM.

    Yields:
        Running VirtualMachineForTests instance.
    """
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_FEDORA,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL, client=unprivileged_client),
        vm_preference=VirtualMachineClusterPreference(name=OS_FLAVOR_FEDORA, client=unprivileged_client),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source,
            storage_class=source_storage_class,
        ),
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


def verify_vms_boot_time_after_storage_migration(
    vm_list: list[VirtualMachineForTests], initial_boot_time: dict[str, str]
) -> None:
    """
    Verify that VMs have not rebooted after storage migration.

    Args:
        vm_list: List of VMs to check
        initial_boot_time: Dictionary mapping VM names to their initial boot times

    Raises:
        AssertionError: If any VM has rebooted (boot time changed)
    """
    rebooted_vms = {}
    for vm in vm_list:
        current_boot_time = get_vm_boot_time(vm=vm)
        if initial_boot_time[vm.name] != current_boot_time:
            rebooted_vms[vm.name] = {"initial": initial_boot_time[vm.name], "current": current_boot_time}
    assert not rebooted_vms, f"Boot time changed for VMs:\n {rebooted_vms}"


def verify_vm_storage_class_updated(vm: VirtualMachineForTests, target_storage_class: str) -> None:
    vm_pvcs_names = get_vm_dv_names(vm=vm)
    failed_pvc_storage_check = {}
    for pvc_name in vm_pvcs_names:
        pvc_storage_class = PersistentVolumeClaim(
            client=vm.client, namespace=vm.namespace, name=pvc_name
        ).instance.spec.storageClassName
        if pvc_storage_class != target_storage_class:
            failed_pvc_storage_check[pvc_name] = pvc_storage_class
    assert not failed_pvc_storage_check, (
        f"Failed PVC storage class check. PVC storage class: {failed_pvc_storage_check}"
        f"Doesn't match expected target storage class: {target_storage_class}"
    )


def verify_storage_migration_succeeded(
    vms_boot_time_before_storage_migration: dict[str, str],
    online_vms_for_storage_class_migration: list[VirtualMachineForTests],
    vms_with_written_file_before_migration: list[VirtualMachineForTests],
    target_storage_class: str,
) -> None:
    verify_vms_boot_time_after_storage_migration(
        vm_list=online_vms_for_storage_class_migration, initial_boot_time=vms_boot_time_before_storage_migration
    )
    for vm in vms_with_written_file_before_migration:
        check_file_in_vm(
            vm=vm,
            file_name=FILE_BEFORE_STORAGE_MIGRATION,
            file_content=CONTENT,
        )
        verify_vm_storage_class_updated(vm=vm, target_storage_class=target_storage_class)


def verify_files_in_hotplugged_disks(vm: VirtualMachineForTests, file_name: str, file_content: str) -> None:
    """Verify that a file exists with expected content on all hotplugged disk mount paths.

    Args:
        vm: The VM to check.
        file_name: Name of the file to verify on each mount path.
        file_content: Expected content of the file.
    """
    mismatches = {}
    for mount_path in MOUNT_HOTPLUGGED_DEVICE_PATHS:
        output = run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(f"cat {mount_path}/{file_name}"),
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )[0]
        stripped_output = output.strip()
        if stripped_output != file_content:
            mismatches[mount_path] = f"'{stripped_output}' does not equal '{file_content}'"
    assert not mismatches, f"Data mismatch on hotplugged disk(s): {mismatches}"


def wait_for_storage_migration_phase(
    mig_migration: MultiNamespaceVirtualMachineStorageMigration,
    expected_phase: str = MultiNamespaceVirtualMachineStorageMigration.Status.COMPLETED,
    timeout: int = TIMEOUT_10MIN,
) -> None:
    """Wait for all namespaces in the migration to reach the expected phase.

    Args:
        mig_migration: Migration resource to monitor.
        expected_phase: Phase all namespaces must reach. Defaults to COMPLETED.
        timeout: Maximum wait time in seconds.

    Raises:
        StorageMigrationError: If migration does not reach the expected phase within timeout.
    """
    last_sample = None
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_10SEC,
        func=lambda: mig_migration.instance.status,
    )
    try:
        for sample in samples:
            last_sample = sample
            if sample and sample.namespaces:
                if all(ns.get("phase") == expected_phase for ns in sample.namespaces):
                    return
    except TimeoutExpiredError as err:
        raise StorageMigrationError(
            f"Timeout waiting for storage migration '{mig_migration.name}' to reach phase "
            f"'{expected_phase}'. Last status sample: {last_sample}"
        ) from err


def get_vm_dv_names(vm: VirtualMachineForTests) -> list[str]:
    """Get DataVolume names from VM spec volumes.

    Args:
        vm: VirtualMachine instance to extract DV names from.

    Returns:
        List of DataVolume names referenced by the VM.
    """
    return [
        volume["dataVolume"]["name"]
        for volume in vm.instance.spec.template.spec.volumes
        if "dataVolume" in dict(volume)
    ]


def get_vm_volume_node(vm: VirtualMachineForTests) -> str | None:
    """Return the node hosting the VM's first data volume.

    Reads the ``volume.kubernetes.io/selected-node`` annotation of the PVC backing the VM's
    first DataVolume. Only node-local provisioners (e.g. HPP / hostpath-csi) set this annotation;
    it is ``None`` for storage that is not bound to a specific node.

    Args:
        vm: VM whose first data volume's node is returned.

    Returns:
        The node name hosting the volume, or ``None`` when the PVC has no selected-node annotation.
    """
    pvc_name = get_vm_dv_names(vm=vm)[0]
    return PersistentVolumeClaim(client=vm.client, namespace=vm.namespace, name=pvc_name).selected_node


def verify_source_dvs_deleted(vm: VirtualMachineForTests, source_dv_names: list[str]) -> None:
    """Verify that source DataVolumes are deleted after migration.

    Args:
        vm: VirtualMachine instance (used for client and namespace).
        source_dv_names: List of source DataVolume names to verify deletion.
    """
    for dv_name in source_dv_names:
        dv = DataVolume(client=vm.client, namespace=vm.namespace, name=dv_name)
        assert dv.wait_deleted(), f"Source DataVolume {dv_name} still exists in namespace {vm.namespace}"


def verify_source_dvs_exist(vm: VirtualMachineForTests, source_dv_names: list[str]) -> None:
    """Verify that source DataVolumes still exist after migration.

    Args:
        vm: VirtualMachine instance (used for client and namespace).
        source_dv_names: List of source DataVolume names to verify existence.
    """
    for dv_name in source_dv_names:
        dv = DataVolume(client=vm.client, namespace=vm.namespace, name=dv_name)
        assert dv.exists, f"Source DataVolume {dv_name} was deleted from namespace {vm.namespace}"


def build_namespaces_spec_for_storage_migration(
    vms: list[VirtualMachineForTests], target_storage_class: str
) -> list[dict]:
    """
    Build namespaces spec for MultiNamespaceVirtualMachineStorageMigrationPlan:
    [
        {"name": "namespace1", "virtualMachines": [vm1, vm2, ...]},
        {"name": "namespace2", "virtualMachines": [vm3, ...]},
    ]

    Args:
        vms: List of VMs to include in the migration plan.
        target_storage_class: Target storage class for the migration.

    Returns:
        List of namespace specs with VMs and their target migration PVCs.
    """
    namespaces_dict: dict[str, list] = {}
    for vm in vms:
        # Get volume names from VM spec
        target_migration_pvcs = []
        for volume in vm.instance.spec.template.spec.volumes:
            if "dataVolume" in volume.keys():
                target_migration_pvcs.append({
                    "volumeName": volume.name,
                    "destinationPVC": {
                        "volumeMode": "Auto",
                        "accessModes": ["Auto"],
                        "storageClassName": target_storage_class,
                    },
                })
        # Group VMs by namespace
        namespaces_dict.setdefault(vm.namespace, []).append({
            "name": vm.name,
            "targetMigrationPVCs": target_migration_pvcs,
        })

    return [{"name": ns_name, "virtualMachines": vms} for ns_name, vms in namespaces_dict.items()]


def build_namespaces_spec_with_target_volume_mode(
    vms: list[VirtualMachineForTests], target_storage_class: str, target_volume_mode: str
) -> list[dict]:
    """Build the migration plan namespaces spec with an explicit target volume mode for every PVC.

    Args:
        vms: VMs to include in the migration plan.
        target_storage_class: Target storage class for the migration.
        target_volume_mode: Volume mode of the destination PVCs ("Block" or "Filesystem").

    Returns:
        Namespaces spec for MultiNamespaceVirtualMachineStorageMigrationPlan.
    """
    namespaces_spec = build_namespaces_spec_for_storage_migration(vms=vms, target_storage_class=target_storage_class)
    for namespace_entry in namespaces_spec:
        for vm_entry in namespace_entry["virtualMachines"]:
            for target_pvc in vm_entry["targetMigrationPVCs"]:
                target_pvc["destinationPVC"]["volumeMode"] = target_volume_mode
    return namespaces_spec


def wait_for_storage_migration_in_progress(
    mig_migration: MultiNamespaceVirtualMachineStorageMigration, timeout: int = TIMEOUT_10MIN
) -> None:
    """Wait until all namespaces in the migration are actively migrating VM volumes.

    Args:
        mig_migration: Migration resource to monitor.
        timeout: Maximum wait time in seconds.

    Raises:
        StorageMigrationError: If the migration completes before it is observed in progress,
            or does not reach the in-progress phase within timeout.
    """
    last_sample = None
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_5SEC,
        func=lambda: mig_migration.instance.status,
    )
    try:
        for sample in samples:
            last_sample = sample
            if sample and sample.namespaces:
                phases = {namespace.get("phase") for namespace in sample.namespaces}
                if phases == {STORAGE_MIGRATION_IN_PROGRESS_PHASE}:
                    return
                if mig_migration.Status.COMPLETED in phases:
                    raise StorageMigrationError(
                        f"Storage migration '{mig_migration.name}' completed before it was observed in progress. "
                        f"Status: {sample}"
                    )
    except TimeoutExpiredError as err:
        raise StorageMigrationError(
            f"Timeout waiting for storage migration '{mig_migration.name}' to reach phase "
            f"'{STORAGE_MIGRATION_IN_PROGRESS_PHASE}'. Last status sample: {last_sample}"
        ) from err


def wait_for_offline_storage_migration_completed(mig_migration: MultiNamespaceVirtualMachineStorageMigration) -> None:
    """Wait for a migration that includes offline VMs to complete.

    Args:
        mig_migration: Migration resource to monitor.

    Raises:
        StorageMigrationError: If the migration does not complete within timeout, unless the
            failure matches open bug CNV-99047, in which case the test is marked xfail.
    """
    try:
        wait_for_storage_migration_phase(mig_migration=mig_migration, expected_phase=mig_migration.Status.COMPLETED)
    except StorageMigrationError:
        non_completed_phases = {
            namespace.get("phase")
            for namespace in (mig_migration.instance.status.namespaces or [])
            if namespace.get("phase") != mig_migration.Status.COMPLETED
        }
        if non_completed_phases == {STORAGE_MIGRATION_IN_PROGRESS_PHASE} and is_jira_open(jira_id="CNV-99047"):
            pytest.xfail(reason="Offline VM storage migration stuck in WaitForLiveMigrationToComplete, CNV-99047")
        raise


def verify_vm_pvcs_volume_mode(vm: VirtualMachineForTests, volume_mode: str) -> None:
    """Verify that all PVCs referenced by the VM use the expected volume mode.

    Args:
        vm: VM whose PVCs are checked.
        volume_mode: Expected PVC volume mode.
    """
    mismatched_pvcs = {}
    for pvc_name in get_vm_dv_names(vm=vm):
        pvc_volume_mode = PersistentVolumeClaim(
            client=vm.client, namespace=vm.namespace, name=pvc_name
        ).instance.spec.volumeMode
        if pvc_volume_mode != volume_mode:
            mismatched_pvcs[pvc_name] = pvc_volume_mode
    assert not mismatched_pvcs, f"PVC volume mode does not match expected '{volume_mode}': {mismatched_pvcs}"


def verify_vm_dv_names_unchanged(vm: VirtualMachineForTests, expected_dv_names: list[str]) -> None:
    """Verify that the VM still references its original DataVolumes.

    Args:
        vm: VM to check.
        expected_dv_names: DataVolume names the VM referenced before migration.
    """
    current_dv_names = get_vm_dv_names(vm=vm)
    assert sorted(current_dv_names) == sorted(expected_dv_names), (
        f"VM {vm.name} disk references changed. Expected: {expected_dv_names}, current: {current_dv_names}"
    )


def verify_vm_dv_names_changed(vm: VirtualMachineForTests, original_dv_names: list[str]) -> None:
    """Verify that the VM references new DataVolumes after migration.

    Args:
        vm: VM to check.
        original_dv_names: DataVolume names the VM referenced before migration.
    """
    current_dv_names = get_vm_dv_names(vm=vm)
    assert sorted(current_dv_names) != sorted(original_dv_names), (
        f"VM {vm.name} disk references did not change after migration; still referencing: {current_dv_names}"
    )


def verify_vm_pending_until_storage_migration_completed(
    vm: VirtualMachineForTests,
    mig_migration: MultiNamespaceVirtualMachineStorageMigration,
    timeout: int = TIMEOUT_10MIN,
) -> None:
    """Verify that a VM started during migration does not become ready before its volumes are migrated.

    The VM is sampled until the migration completes. The VM must be observed not ready at least
    once, and it must never be ready while any of its DataVolumes has not succeeded.

    Args:
        vm: VM that was started while the migration was in progress.
        mig_migration: Migration resource to monitor.
        timeout: Maximum wait time in seconds for the migration to complete.

    Raises:
        StorageMigrationError: If the migration does not complete within timeout.
    """
    observed_vm_not_ready = False
    last_sample = None
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_5SEC,
        func=lambda: mig_migration.instance.status,
    )
    try:
        for sample in samples:
            last_sample = sample
            if (
                sample
                and sample.namespaces
                and all(namespace.get("phase") == mig_migration.Status.COMPLETED for namespace in sample.namespaces)
            ):
                break
            if not vm.ready:
                observed_vm_not_ready = True
                continue
            not_succeeded_dvs = {}
            for dv_name in get_vm_dv_names(vm=vm):
                dv_phase = DataVolume(client=vm.client, namespace=vm.namespace, name=dv_name).instance.status.phase
                if dv_phase != DataVolume.Status.SUCCEEDED:
                    not_succeeded_dvs[dv_name] = dv_phase
            assert not not_succeeded_dvs, (
                f"VM {vm.name} became ready before its volumes were migrated. DataVolume phases: {not_succeeded_dvs}"
            )
    except TimeoutExpiredError as err:
        raise StorageMigrationError(
            f"Timeout waiting for storage migration '{mig_migration.name}' to complete. "
            f"Last status sample: {last_sample}"
        ) from err
    assert observed_vm_not_ready, f"VM {vm.name} was never observed in a pending state during storage migration"


def mount_hotplugged_disks(vm: VirtualMachineForTests, hotplug_volume_names: list[str]) -> None:
    """Mount already formatted hotplugged disks in a VM, e.g. after the VM was restarted.

    Args:
        vm: Running VM with the hotplugged disks attached.
        hotplug_volume_names: VM volume names of the hotplugged disks.
    """
    for volume_name in hotplug_volume_names:
        wait_for_vm_volume_ready(vm=vm, volume_name=volume_name)
    for device, mount_path in zip(HOTPLUGGED_DEVICES, MOUNT_HOTPLUGGED_DEVICE_PATHS, strict=True):
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=[shlex.split(cmd) for cmd in [f"sudo mkdir -p {mount_path}", f"sudo mount {device} {mount_path}"]],
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
        )
