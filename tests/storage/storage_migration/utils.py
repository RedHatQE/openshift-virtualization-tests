import shlex

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
    MOUNT_HOTPLUGGED_DEVICE_PATHS,
)
from tests.storage.utils import check_file_in_vm
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.instance_types import U1_SMALL
from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5SEC, TIMEOUT_10MIN, TIMEOUT_10SEC
from utilities.exceptions import StorageMigrationError
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, get_vm_boot_time, running_vm


def create_cleanup_test_vm(
    unprivileged_client,
    namespace_name: str,
    golden_images_namespace,
    source_storage_class: str,
    cpu_for_migration: str,
    vm_name: str,
):
    """Create a fedora VM for retention policy testing.

    Args:
        unprivileged_client: Kubernetes client for VM creation.
        namespace_name: Namespace where the VM will be created.
        golden_images_namespace: Namespace containing golden image data sources.
        source_storage_class: Storage class for the VM's DataVolume.
        cpu_for_migration: CPU model for migration compatibility.
        vm_name: Name for the VM.

    Yields:
        Running VirtualMachineForTests instance.
    """
    golden_images_fedora_data_source = DataSource(
        namespace=golden_images_namespace.name,
        name=OS_FLAVOR_FEDORA,
        client=golden_images_namespace.client,
        ensure_exists=True,
    )
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_FEDORA,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL, client=unprivileged_client),
        vm_preference=VirtualMachineClusterPreference(name=OS_FLAVOR_FEDORA, client=unprivileged_client),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_images_fedora_data_source,
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
    vm_pvcs_names = [
        volume["dataVolume"]["name"]
        for volume in vm.instance.spec.template.spec.volumes
        if "dataVolume" in dict(volume)
    ]
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
    expected_phase: str,
    timeout: int = TIMEOUT_10MIN,
) -> None:
    """Wait for all namespaces in the migration to reach the expected phase.

    Args:
        mig_migration: Migration resource to monitor.
        expected_phase: Phase all namespaces must reach (e.g. mig_migration.Status.COMPLETED).
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


def get_vm_source_dv_names(vm: VirtualMachineForTests) -> list[str]:
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
