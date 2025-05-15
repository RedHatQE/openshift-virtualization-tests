import re
import shlex
from typing import Any, Literal

from ocp_resources.controller_revision import ControllerRevision
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
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


def verify_no_deprecated_field_in_api(
    crd_to_test: CustomResourceDefinition, cluster_resources_list: list[VirtualMachineClusterPreference]
):
    current_api_version_dict = [
        version_dict
        for version_dict in crd_to_test.instance.to_dict()["spec"]["versions"]
        if version_dict.get("deprecated") is not True
    ][0]
    api_deprecated_fields = find_deprecated_fields_in_api(api_dict=current_api_version_dict)
    deprecated_fields_in_use = []
    for deprecated_field in api_deprecated_fields:
        for vm_cluster_preference in cluster_resources_list:
            if is_field_used(field_path=deprecated_field, resource_dict=vm_cluster_preference.instance.to_dict()):
                deprecated_fields_in_use.append(deprecated_field)
    assert not deprecated_fields_in_use, f"The following deprecated fields are used: {deprecated_fields_in_use}"


def find_deprecated_fields_in_api(api_dict: dict[str, Any] | list[Any], path: str = "") -> list[str]:
    deprecated_fields = []

    if isinstance(api_dict, dict):
        for key, value in api_dict.items():
            current_path = f"{path}.{key}" if path else key
            if key == "description" and isinstance(value, str) and "deprecated" in value.lower():
                deprecated_fields.append(path)
            elif isinstance(value, (dict, list)):
                deprecated_fields.extend(find_deprecated_fields_in_api(value, current_path))
    elif isinstance(api_dict, list):
        for index, item in enumerate(api_dict):
            current_path = f"{path}[{index}]"
            deprecated_fields.extend(find_deprecated_fields_in_api(item, current_path))

    return deprecated_fields


def is_field_used(field_path: str, resource_dict: dict) -> bool:
    keys = re.split(r"\.properties\.", field_path.split(".spec", 1)[-1])
    current_dict_value = resource_dict
    for key in keys:
        if not isinstance(current_dict_value, dict) or key not in current_dict_value:
            return False
        current_dict_value = current_dict_value[key]
    return True
