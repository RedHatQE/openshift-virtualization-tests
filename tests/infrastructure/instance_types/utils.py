import re
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


def check_dmesg_for_pattern(vm, dmesg_pattern):
    return run_ssh_commands(host=vm.ssh_exec, commands=shlex.split(f"sudo dmesg | grep -i '{dmesg_pattern}' || true"))[
        0
    ]


def assert_dmesg(vm, dmesg_pattern, expected_status):
    output = check_dmesg_for_pattern(vm=vm, dmesg_pattern=dmesg_pattern)
    assert re.search(dmesg_pattern, output, re.IGNORECASE), (
        f"Expected pattern '{expected_status}' not found in dmesg logs. Found: {output}"
    )


def assert_secure_boot_mokutil_status(vm, expected_status):
    output = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("mokutil --sb-state"))[0].strip().lower()
    assert expected_status.lower() in re.sub(r"\s+", " ", output.strip()).lower(), (
        f"Expected Secure Boot status '{expected_status}' not found inside the guest OS. Found: {output}"
    )


def assert_kernel_lockdown_mode(vm, lockdown_mode="none"):
    output = (
        run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("cat /sys/kernel/security/lockdown"))[0].strip().lower()
    )
    guest_lockdown_mode = output.split("[")[1].split("]")[0]
    assert guest_lockdown_mode != lockdown_mode, (
        f"Kernel lockdown mode is '{guest_lockdown_mode}'. Secure Boot may not be enforcing security restrictions. "
        f"Expected mode: {lockdown_mode}"
    )
