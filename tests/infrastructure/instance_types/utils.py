import shlex
from typing import Literal

from ocp_resources.controller_revision import ControllerRevision
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine import VirtualMachine
from pyhelper_utils.shell import run_ssh_commands


def get_mismatch_vendor_label(resources_list):
    failed_labels = {}
    for resource in resources_list:
        vendor_label = resource.labels[f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/vendor"]
        if vendor_label != "redhat.com":
            failed_labels[resource.name] = vendor_label
    return failed_labels


def assert_mismatch_vendor_label(resources_list):
    failed_labels = get_mismatch_vendor_label(resources_list=resources_list)
    assert not failed_labels, f"The following resources have miss match vendor label: {failed_labels}"


def get_controller_revision(
    vm_instance: VirtualMachine, ref_type: Literal["instancetype", "preference"]
) -> ControllerRevision:
    ref_mapping = {
        "instancetype": vm_instance.instance.status.instancetypeRef.controllerRevisionRef.name,
        "preference": vm_instance.instance.status.preferenceRef.controllerRevisionRef.name,
    }

    return ControllerRevision(
        name=ref_mapping[ref_type],
        namespace=vm_instance.namespace,
    )


def assert_instance_revision_and_memory_update(
    vm_for_test: VirtualMachine, old_revision_name: str, updated_memory: str
) -> None:
    guest_memory = vm_for_test.vmi.instance.spec.domain.memory.guest
    assert vm_for_test.instance.status.instancetypeRef.controllerRevisionRef.name != old_revision_name, (
        "The revisionName is still {old_revision_name}, not updated after editing"
    )
    assert guest_memory == updated_memory, (
        "The Guest Memory in VMI is {guest_memory}, not updated to {updated_memory} after editing"
    )


def assert_secure_boot_dmesg(vm: VirtualMachine) -> None:
    output = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("sudo dmesg | grep -i secureboot"))[0]
    assert "enabled" in output.lower(), f"Secure Boot was not enabled at boot time. Found: {output}"


def assert_secure_boot_mokutil_status(vm: VirtualMachine) -> None:
    output = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("mokutil --sb-state"))[0].lower()
    assert "enabled" in output, f"Secure Boot is not enabled. Found: {output}"


def assert_kernel_lockdown_mode(vm: VirtualMachine) -> None:
    output = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("cat /sys/kernel/security/lockdown"))[0]
    assert "[none]" not in output, f"Kernel lockdown mode is not '[none]'. Found: {output}"
