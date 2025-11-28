import shlex
from contextlib import contextmanager

from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pyhelper_utils.shell import run_ssh_commands

from tests.utils import create_rhel_vm_from_data_source
from utilities.storage import write_file
from utilities.virt import wait_for_ssh_connectivity


@contextmanager
def create_vm_for_snapshot_upgrade_tests(
    vm_name,
    namespace,
    client,
    storage_class_for_snapshot,
    cpu_model,
    rhel10_data_source_scope_module,
):
    with create_rhel_vm_from_data_source(
        storage_class=storage_class_for_snapshot,
        namespace=namespace,
        client=client,
        vm_name=f"vm-{vm_name}",
        data_source=rhel10_data_source_scope_module,
        cpu_model=cpu_model,
    ) as vm:
        write_file(
            vm=vm,
            filename="first-file.txt",
            content="first-file",
        )
        yield vm


@contextmanager
def create_snapshot_for_upgrade(vm, client):
    """Creating a snapshot of vm and adding a text file to the vm"""
    with VirtualMachineSnapshot(
        name=f"snapshot-{vm.name}",
        namespace=vm.namespace,
        vm_name=vm.name,
        client=client,
    ) as vm_snapshot:
        vm_snapshot.wait_snapshot_done()
        write_file(
            vm=vm,
            filename="second-file.txt",
            content="second-file",
        )
        yield vm_snapshot
