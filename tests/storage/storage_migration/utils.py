from contextlib import contextmanager

from kubernetes.dynamic import DynamicClient
from ocp_resources.data_source import DataSource
from ocp_resources.pod import Pod
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from utilities import console
from utilities.constants import LS_COMMAND, OS_FLAVOR_FEDORA, TIMEOUT_20SEC, U1_SMALL
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

FILE_BEFORE_STORAGE_MIGRATION = "file-before-storage-migration.txt"
CONTENT = "hey"


@contextmanager
def create_vm_from_data_source_with_instance_type(
    vm_name: str,
    namespace: str,
    client: DynamicClient,
    data_source: DataSource,
    storage_class: str,
) -> VirtualMachine:
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace,
        os_flavor=OS_FLAVOR_FEDORA,
        client=client,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(name=OS_FLAVOR_FEDORA),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source,
            storage_class=storage_class,
        ),
    ) as vm:
        running_vm(vm=vm)
        yield vm


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
