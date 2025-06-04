from kubernetes.dynamic import DynamicClient
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.virtual_machine import VirtualMachine

from tests.storage.storage_migration.constants import CONTENT, FILE_BEFORE_STORAGE_MIGRATION
from utilities import console
from utilities.constants import LS_COMMAND, TIMEOUT_20SEC
from utilities.virt import get_vm_boot_time


def get_source_virt_launcher_pod(client: DynamicClient, vm: VirtualMachine) -> Pod:
    source_pod_name = vm.vmi.instance.to_dict().get("status", {}).get("migrationState", {}).get("sourcePod")
    assert source_pod_name, f"Source pod name is not found in VMI status.migrationState.sourcePod for VM '{vm.name}'"
    return Pod(client=client, name=source_pod_name, namespace=vm.namespace, ensure_exists=True)


def check_file_in_vm(vm: VirtualMachine, file_name: str, file_content: str) -> None:
    if not vm.ready:
        vm.start(wait=True)
    with console.Console(vm=vm) as vm_console:
        vm_console.sendline(LS_COMMAND)
        vm_console.expect(file_name, timeout=TIMEOUT_20SEC)
        vm_console.sendline(f"cat {file_name}")
        vm_console.expect(file_content, timeout=TIMEOUT_20SEC)


def verify_vms_boot_time_after_storage_migration(
    vm_list: list[VirtualMachine], initial_boot_time: dict[str, str]
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


def verify_vm_storage_class_updated(vm: VirtualMachine, target_storage_class: str) -> None:
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
    online_vms_for_storage_class_migration: list[VirtualMachine],
    vms_with_written_file_before_migration: list[VirtualMachine],
    target_storage_class: str,
) -> None:
    verify_vms_boot_time_after_storage_migration(
        vm_list=online_vms_for_storage_class_migration,
        initial_boot_time=vms_boot_time_before_storage_migration,
    )
    for vm in vms_with_written_file_before_migration:
        check_file_in_vm(
            vm=vm,
            file_name=FILE_BEFORE_STORAGE_MIGRATION,
            file_content=CONTENT,
        )
        verify_vm_storage_class_updated(vm=vm, target_storage_class=target_storage_class)
