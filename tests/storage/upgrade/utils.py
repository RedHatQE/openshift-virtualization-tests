from contextlib import contextmanager

from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.storage.upgrade.constants import (
    UPGRADE_FIRST_FILE_CONTENT,
    UPGRADE_FIRST_FILE_NAME,
    UPGRADE_SECOND_FILE_CONTENT,
    UPGRADE_SECOND_FILE_NAME,
)
from utilities.constants import OS_FLAVOR_RHEL, RHEL10_PREFERENCE, U1_SMALL
from utilities.storage import data_volume_template_with_source_ref_dict, write_file_via_ssh
from utilities.virt import VirtualMachineForTests, running_vm


@contextmanager
def create_vm_for_snapshot_upgrade_tests(
    vm_name,
    namespace,
    client,
    storage_class_for_snapshot,
    cpu_model,
    data_source,
):
    with VirtualMachineForTests(
        name=f"vm-{vm_name}",
        namespace=namespace,
        client=client,
        os_flavor=OS_FLAVOR_RHEL,
        vm_instance_type=VirtualMachineClusterInstancetype(client=client, name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(client=client, name=RHEL10_PREFERENCE),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source,
            storage_class=storage_class_for_snapshot,
        ),
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        cpu_model=cpu_model,
    ) as vm:
        running_vm(vm=vm)
        write_file_via_ssh(
            vm=vm,
            filename=UPGRADE_FIRST_FILE_NAME,
            content=UPGRADE_FIRST_FILE_CONTENT,
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
        write_file_via_ssh(
            vm=vm,
            filename=UPGRADE_SECOND_FILE_NAME,
            content=UPGRADE_SECOND_FILE_CONTENT,
        )
        yield vm_snapshot
