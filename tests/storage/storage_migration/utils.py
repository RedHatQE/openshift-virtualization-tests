from ocp_resources.pod import Pod
from ocp_resources.virtual_machine import VirtualMachine

from utilities import console
from utilities.constants import LS_COMMAND, TIMEOUT_20SEC
from utilities.virt import get_vm_boot_time

FILE_BEFORE_STORAGE_MIGRATION = "file-before-storage-migration"
CONTENT = "some-content"


def get_source_virt_launcher_pod(vm: VirtualMachine) -> Pod:
    source_pod_name = vm.vmi.instance.to_dict().get("status", {}).get("migrationState", {}).get("sourcePod")
    assert source_pod_name, "Source pod name is not found in VMI status.migrationState.sourcePod"
    return Pod(name=source_pod_name, namespace=vm.namespace, ensure_exists=True)


def check_file_in_vm(vm: VirtualMachine, file_name: str, file_content: str) -> None:
    if not vm.ready:
        vm.start(wait=True)
    with console.Console(vm=vm) as vm_console:
        vm_console.sendline(LS_COMMAND)
        vm_console.expect(file_name, timeout=TIMEOUT_20SEC)
        vm_console.sendline(f"cat {file_name}")
        vm_console.expect(file_content, timeout=TIMEOUT_20SEC)


def verify_linux_vms_boot_time_after_storage_migration(
    vm_list: list[VirtualMachine], initial_boot_time: dict[VirtualMachine, str]
) -> None:
    rebooted_vms = {}
    for vm in vm_list:
        current_boot_time = get_vm_boot_time(vm=vm)
        if initial_boot_time[vm.name] != current_boot_time:
            rebooted_vms[vm.name] = {"initial": initial_boot_time[vm.name], "current": current_boot_time}
    assert not rebooted_vms, f"Boot time changed for VMs:\n {rebooted_vms}"
