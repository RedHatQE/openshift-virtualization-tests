import shlex
from typing import Any, Literal

from ocp_resources.controller_revision import ControllerRevision
from ocp_resources.resource import Resource
from pyhelper_utils.shell import run_ssh_commands

from utilities.constants import Images
from utilities.virt import VirtualMachineForTests


def extract_resources_from_cluster_preference_spec(
    cluster_preference_spec: dict[str, Any],
) -> tuple[str, int | None, int | None, int | None]:
    """Derive VM CPU and memory sizing from a cluster preference spec.

    Maps requirements.cpu.guest and cpu.preferredCPUTopology onto sockets,
    cores, and threads for VirtualMachineForTests. Unset topology defaults
    to sockets.

    Args:
        cluster_preference_spec (dict): VirtualMachineClusterPreference.spec
            content.

    Returns:
        A tuple (memory_guest, sockets, cores, threads).
        memory_guest (str): Guest memory from requirements.memory.guest, or
            Images.Rhel.DEFAULT_MEMORY_SIZE when unset.
        sockets (int | None): Socket count, or None when the preference has
            no requirements.cpu.guest.
        cores (int | None): Core count, or None when the preference has no
            requirements.cpu.guest.
        threads (int | None): Thread count, or None when the preference has
            no requirements.cpu.guest.
    """
    memory_guest = (
        cluster_preference_spec.get("requirements", {}).get("memory", {}).get("guest")
        or Images.Rhel.DEFAULT_MEMORY_SIZE
    )

    cpu_guest = cluster_preference_spec.get("requirements", {}).get("cpu", {}).get("guest")
    if not cpu_guest:
        return memory_guest, None, None, None

    sockets = cores = threads = 1
    if cpu_guest > 1:
        cpu_preferences = cluster_preference_spec.get("cpu", {})
        topology = cpu_preferences.get("preferredCPUTopology", "sockets").removeprefix("prefer").lower()
        if topology == "cores":
            cores = cpu_guest
        elif topology == "spread":
            spread_options = cpu_preferences.get("spreadOptions", {})
            ratio = spread_options.get("ratio", 2)
            across = spread_options.get("across", "SocketsCores")
            if across == "SocketsCoresThreads":
                threads = 2
                cores = ratio
                sockets = cpu_guest // 2 // ratio
            else:
                cores = ratio
                sockets = cpu_guest // ratio
        else:
            sockets = cpu_guest

    return memory_guest, sockets, cores, threads


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
    vm_instance: VirtualMachineForTests, ref_type: Literal["instancetype", "preference"]
) -> ControllerRevision:
    ref_mapping = {
        "instancetype": vm_instance.instance.status.instancetypeRef.controllerRevisionRef.name,
        "preference": vm_instance.instance.status.preferenceRef.controllerRevisionRef.name,
    }

    return ControllerRevision(
        client=vm_instance.client,
        name=ref_mapping[ref_type],
        namespace=vm_instance.namespace,
    )


def assert_instance_revision_and_memory_update(
    vm_for_test: VirtualMachineForTests, old_revision_name: str, updated_memory: str
) -> None:
    guest_memory = vm_for_test.vmi.instance.spec.domain.memory.guest
    assert vm_for_test.instance.status.instancetypeRef.controllerRevisionRef.name != old_revision_name, (
        "The revisionName is still {old_revision_name}, not updated after editing"
    )
    assert guest_memory == updated_memory, (
        "The Guest Memory in VMI is {guest_memory}, not updated to {updated_memory} after editing"
    )


def assert_secure_boot_dmesg(vm: VirtualMachineForTests) -> None:
    output = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("sudo dmesg | grep -i secureboot"))[0]
    assert "enabled" in output.lower(), f"Secure Boot was not enabled at boot time. Found: {output}"


def assert_kernel_lockdown_mode(vm: VirtualMachineForTests) -> None:
    output = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("cat /sys/kernel/security/lockdown"))[0]
    assert "[none]" not in output, f"Kernel lockdown mode is not '[none]'. Found: {output}"
