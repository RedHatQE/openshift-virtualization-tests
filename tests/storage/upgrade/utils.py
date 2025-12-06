from contextlib import contextmanager

from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from utilities.constants import OS_FLAVOR_RHEL, U1_SMALL
from utilities.storage import data_volume_template_with_source_ref_dict, write_file_via_ssh
from utilities.virt import VirtualMachineForTests, running_vm, wait_for_ssh_connectivity


@contextmanager
def create_vm_for_snapshot_upgrade_tests(
    vm_name,
    namespace,
    client,
    storage_class_for_snapshot,
    cpu_model,
    rhel10_data_source_scope_session,
):
    with VirtualMachineForTests(
        name=f"vm-{vm_name}",
        namespace=namespace,
        client=client,
        os_flavor=OS_FLAVOR_RHEL,
        vm_instance_type=VirtualMachineClusterInstancetype(client=client, name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(client=client, name="rhel.10"),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel10_data_source_scope_session,
            storage_class=storage_class_for_snapshot,
        ),
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        cpu_model=cpu_model,
    ) as vm:
        running_vm(vm=vm)
        wait_for_ssh_connectivity(vm=vm)
        write_file_via_ssh(
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
        wait_for_ssh_connectivity(vm=vm)
        write_file_via_ssh(
            vm=vm,
            filename="second-file.txt",
            content="second-file",
        )
        yield vm_snapshot
