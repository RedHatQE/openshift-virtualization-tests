from ocp_resources.pod import Pod
from ocp_resources.virtual_machine import VirtualMachine

from utilities import console
from utilities.constants import LS_COMMAND, TIMEOUT_20SEC

FILE_BEFORE_STORAGE_MIGRATION = "file-before-storage-migration"
CONTENT = "some-content"


def get_source_virt_launcher_pod(vm: VirtualMachine) -> Pod:
    source_pod_name = vm.vmi.instance.to_dict().get("status", {}).get("migrationState", {}).get("sourcePod")
    assert source_pod_name, "Source pod name is not found in VMI status.migrationState.sourcePod"
    source_pod = Pod(name=source_pod_name, namespace=vm.namespace)
    assert source_pod.exists, f"Pod {source_pod_name} is not found"
    return source_pod


def check_file_in_vm(vm: VirtualMachine, file_name: str, file_content: str) -> None:
    with console.Console(vm=vm) as vm_console:
        vm_console.sendline(LS_COMMAND)
        vm_console.expect(file_name, timeout=TIMEOUT_20SEC)
        vm_console.sendline(f"cat {file_name}")
        vm_console.expect(file_content, timeout=TIMEOUT_20SEC)
