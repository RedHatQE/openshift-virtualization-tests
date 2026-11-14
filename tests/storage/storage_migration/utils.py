import shlex

import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.multi_namespace_virtual_machine_storage_migration import MultiNamespaceVirtualMachineStorageMigration
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutSampler

from tests.storage.storage_migration.constants import (
    CONTENT,
    FILE_BEFORE_STORAGE_MIGRATION,
    MOUNT_HOTPLUGGED_DEVICE_PATH,
    NO_STORAGE_CLASS_FAILURE_MESSAGE,
)
from utilities import console
from utilities.constants import (
    LS_COMMAND,
    OS_FLAVOR_FEDORA,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_10SEC,
    TIMEOUT_20SEC,
    U1_SMALL,
)
from utilities.exceptions import StorageMigrationError
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, get_vm_boot_time, running_vm


def create_fedora_vm_with_instance_type(
    unprivileged_client,
    namespace_name: str,
    data_source: DataSource,
    source_storage_class: str,
    cpu_for_migration: str,
    vm_name: str,
):
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_FEDORA,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL, client=unprivileged_client),
        vm_preference=VirtualMachineClusterPreference(name=OS_FLAVOR_FEDORA, client=unprivileged_client),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source, storage_class=source_storage_class
        ),
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


def check_file_in_vm(vm: VirtualMachineForTests, file_name: str, file_content: str) -> None:
    if not vm.ready:
        vm.start(wait=True)
    with console.Console(vm=vm) as vm_console:
        vm_console.sendline(LS_COMMAND)
        vm_console.expect(file_name, timeout=TIMEOUT_20SEC)
        vm_console.sendline(f"cat {file_name}")
        vm_console.expect(file_content, timeout=TIMEOUT_20SEC)


def verify_vms_boot_time_after_storage_migration(vm_list, initial_boot_time):
    rebooted_vms = {}
    for vm in vm_list:
        current_boot_time = get_vm_boot_time(vm=vm)
        if initial_boot_time[vm.name] != current_boot_time:
            rebooted_vms[vm.name] = {"initial": initial_boot_time[vm.name], "current": current_boot_time}
    assert not rebooted_vms, f"Boot time changed for VMs:\n {rebooted_vms}"


def verify_vm_storage_class_updated(vm, target_storage_class):
    vm_pvcs_names = get_vm_dv_names(vm=vm)
    failed = {}
    for pvc_name in vm_pvcs_names:
        pvc_storage_class = PersistentVolumeClaim(
            client=vm.client, namespace=vm.namespace, name=pvc_name
        ).instance.spec.storageClassName
        if pvc_storage_class != target_storage_class:
            failed[pvc_name] = pvc_storage_class
    assert not failed, (
        f"Failed PVC storage class check. PVC storage class: {failed} Doesn't match expected target storage class: {target_storage_class}"
    )


def verify_storage_migration_succeeded(
    vms_boot_time_before_storage_migration,
    online_vms_for_storage_class_migration,
    vms_with_written_file_before_migration,
    target_storage_class,
):
    verify_vms_boot_time_after_storage_migration(
        online_vms_for_storage_class_migration, vms_boot_time_before_storage_migration
    )
    for vm in vms_with_written_file_before_migration:
        check_file_in_vm(vm=vm, file_name=FILE_BEFORE_STORAGE_MIGRATION, file_content=CONTENT)
        verify_vm_storage_class_updated(vm=vm, target_storage_class=target_storage_class)


def get_storage_class_for_storage_migration(storage_class, cluster_storage_classes_names):
    if storage_class in cluster_storage_classes_names:
        return storage_class
    pytest.fail(
        NO_STORAGE_CLASS_FAILURE_MESSAGE.format(
            storage_class=storage_class, cluster_storage_classes_names=cluster_storage_classes_names
        )
    )


def verify_file_in_hotplugged_disk(vm, file_name, file_content):
    output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"cat {MOUNT_HOTPLUGGED_DEVICE_PATH}/{file_name}"),
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
    )[0]
    assert output.strip() == file_content, f"'{output}' does not equal '{file_content}'"


def wait_for_storage_migration_phase(
    mig_migration, expected_phase=MultiNamespaceVirtualMachineStorageMigration.Status.COMPLETED, timeout=TIMEOUT_10MIN
):
    for sample in TimeoutSampler(
        wait_timeout=timeout, sleep=TIMEOUT_10SEC, func=lambda: mig_migration.instance.status.phase
    ):
        if sample == expected_phase:
            return
    raise StorageMigrationError(f"Migration did not reach phase {expected_phase}")


def get_vm_dv_names(vm):
    return [
        volume.data_volume_template.name
        for volume in vm.instance.spec.template.spec.volumes
        if volume.data_volume_template
    ]


def build_namespaces_spec_for_storage_migration(*args, **kwargs):
    return []


def wait_for_storage_migration_completed(mig_migration, timeout=TIMEOUT_10MIN):
    return wait_for_storage_migration_phase(mig_migration=mig_migration, timeout=timeout)
