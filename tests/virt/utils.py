from __future__ import annotations

import logging
import shlex
from contextlib import contextmanager

import bitmath
from kubernetes.dynamic import DynamicClient
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.gpu.constants import (
    GPU_PRETTY_NAME_STR,
    MDEV_NAME_STR,
    MDEV_TYPE_STR,
    VGPU_DEVICE_NAME_STR,
    VGPU_PRETTY_NAME_STR,
)
from utilities.constants.hco import DEFAULT_HCO_CONDITIONS
from utilities.constants.images import OS_FLAVOR_WINDOWS
from utilities.constants.timeouts import (
    TCP_TIMEOUT_30SEC,
    TIMEOUT_1MIN,
    TIMEOUT_1SEC,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
    TIMEOUT_30SEC,
)
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    is_hco_tainted,
    update_hco_annotations,
    wait_for_hco_conditions,
)
from utilities.virt import (
    VirtualMachineForTests,
    fetch_pid_from_linux_vm,
    get_vm_boot_time,
    kill_processes_by_name_linux,
    migrate_vm_and_verify,
    start_and_fetch_processid_on_linux_vm,
    verify_vm_migrated,
    wait_for_migration_finished,
    wait_for_updated_kv_value,
)

LOGGER = logging.getLogger(__name__)


@contextmanager
def append_feature_gate_to_hco(feature_gate, resource, client, namespace):
    with update_hco_annotations(
        admin_client=client,
        resource=resource,
        path="developerConfiguration/featureGates",
        value=feature_gate,
    ):
        wait_for_updated_kv_value(
            admin_client=client,
            hco_namespace=namespace,
            path=[
                "developerConfiguration",
                "featureGates",
            ],
            value=feature_gate,
        )
        wait_for_hco_conditions(
            admin_client=client,
            hco_namespace=namespace,
            expected_conditions={
                **DEFAULT_HCO_CONDITIONS,
                "TaintedConfiguration": Resource.Condition.Status.TRUE,
            },
        )
        yield
    assert not is_hco_tainted(admin_client=client, hco_namespace=namespace.name)


@contextmanager
def running_sleep_in_linux(vm):
    process = "sleep"
    kill_processes_by_name_linux(vm=vm, process_name=process, check_rc=False)
    pid_orig = start_and_fetch_processid_on_linux_vm(vm=vm, process_name=process, args="1000", use_nohup=True)
    yield
    pid_after = fetch_pid_from_linux_vm(vm=vm, process_name=process)
    kill_processes_by_name_linux(vm=vm, process_name=process)
    assert pid_orig == pid_after, f"PID mismatch: {pid_orig} != {pid_after}"


def get_stress_ng_pid(ssh_exec, windows=False):
    stress = "stress-ng"
    LOGGER.info(f"Get pid of {stress}")
    command_prefix = "wsl" if windows else ""
    tcp_timeout = TIMEOUT_1MIN if windows else TCP_TIMEOUT_30SEC

    return run_ssh_commands(
        host=ssh_exec,
        commands=shlex.split(f"{command_prefix} bash -c 'pgrep {stress}'"),
        tcp_timeout=tcp_timeout,
        wait_timeout=TIMEOUT_2MIN,
    )[0].split("\n")[0]


def verify_stress_ng_pid_not_changed(vm, initial_pid, windows=False):
    current_stress_ng_pid = get_stress_ng_pid(
        ssh_exec=vm.ssh_exec,
        windows=windows,
    )
    assert initial_pid == current_stress_ng_pid, (
        f"stress-ng pid changed. Before: {initial_pid}. Current: {current_stress_ng_pid}"
    )


def migrate_and_verify_multi_vms(client: DynamicClient, vm_list: list[VirtualMachineForTests]) -> None:
    vms_dict = {}
    failed_migrations_list = []

    for vm in vm_list:
        vms_dict[vm.name] = {
            "node_before": vm.vmi.node,
            "vm_mig": migrate_vm_and_verify(vm=vm, client=client, wait_for_migration_success=False),
        }

    for vm in vm_list:
        migration = vms_dict[vm.name]["vm_mig"]
        wait_for_migration_finished(migration=migration)
        migration.clean_up()

    for vm in vm_list:
        vm_sources = vms_dict[vm.name]
        try:
            verify_vm_migrated(vm=vm, node_before=vm_sources["node_before"])
        except AssertionError, TimeoutExpiredError:
            failed_migrations_list.append(vm.name)

    assert not failed_migrations_list, f"Some VMs failed to migrate - {failed_migrations_list}"


# AAQ
def check_pod_in_gated_state(pod):
    if pod.status == Pod.Status.PENDING:
        pod_spec = pod.instance.spec
        return pod_spec.schedulingGates and any(
            gates["name"] == "ApplicationAwareQuotaGate" for gates in pod_spec.schedulingGates
        )


def wait_when_pod_in_gated_state(pod):
    LOGGER.info("Waiting for pod in schedulingGated state")
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
        func=check_pod_in_gated_state,
        pod=pod,
    )
    # POD created in schedulingGated state, check it was not switched to Running state in several seconds
    consecutive_check = 0
    try:
        for sample in samples:
            if sample:
                consecutive_check += 1
                if consecutive_check == 3:
                    return
            else:
                consecutive_check = 0
    except TimeoutExpiredError:
        LOGGER.error(f"The POD in {pod.status} state")
        raise


def check_arq_status_values(current_values, expected_values):
    flatten_expected_values = flatten_dict(dictionary=expected_values)
    flatten_arq_status = flatten_dict(dictionary=current_values)
    failed_status_fields = {}
    for key, value in flatten_arq_status.items():
        if key in flatten_expected_values:
            if value != str(flatten_expected_values[key]):
                failed_status_fields[key] = f"current value: {value}, expected: {flatten_expected_values[key]}"
        else:
            if value != "0":
                failed_status_fields[key] = f"current value: {value}, expected: 0"
    assert not failed_status_fields, f"Incorrect fields in ARQ status: {failed_status_fields}"


# POD shows resources as: {'limits': {'cpu': '2'}}
# ARQ shows status as: {'limits.cpu': '2'}
# Need to flatten dicts to be able to compare values
def flatten_dict(dictionary, parent_key=""):
    items = []
    for key, value in dictionary.items():
        new_key = f"{parent_key}.{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key).items())
        else:
            items.append((new_key, value))
    return dict(items)


def wait_for_virt_launcher_pod(vmi, privileged_client: DynamicClient):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_30SEC,
        sleep=TIMEOUT_1SEC,
        func=lambda: vmi.get_virt_launcher_pod(privileged_client=privileged_client),
    )
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Virt-laucher pod for VMI {vmi.name} was not found!")
        raise


def validate_machine_type(vm, expected_machine_type, admin_client):
    vm_machine_type = vm.instance.spec.template.spec.domain.machine.type
    vmi_machine_type = vm.vmi.instance.spec.domain.machine.type

    assert vm_machine_type == vmi_machine_type == expected_machine_type, (
        "Created VM's machine type does not match the request. "
        f"Expected: {expected_machine_type} VM: {vm_machine_type}, VMI: {vmi_machine_type}"
    )
    vmi_xml_machine_type = vm.vmi.get_xml_dict(privileged_client=admin_client)["domain"]["os"]["type"]["@machine"]
    assert vmi_xml_machine_type == expected_machine_type, (
        f"libvirt machine type {vmi_xml_machine_type} does not match expected type {expected_machine_type}"
    )


def patch_hco_cr_with_mdev_permitted_hostdevices(admin_client, hyperconverged_resource, supported_gpu_device):
    required_keys = [MDEV_TYPE_STR, MDEV_NAME_STR, VGPU_DEVICE_NAME_STR]
    missing_keys = [key for key in required_keys if key not in supported_gpu_device]
    if missing_keys:
        raise ValueError(f"Missing required keys in supported_gpu_device: {missing_keys}")
    with ResourceEditorValidateHCOReconcile(
        admin_client=admin_client,
        patches={
            hyperconverged_resource: {
                "spec": {
                    "virtualization": {
                        "permittedHostDevices": {
                            "mediatedDevices": [
                                {
                                    "externalResourceProvider": True,
                                    "mdevNameSelector": supported_gpu_device[MDEV_NAME_STR],
                                    "resourceName": supported_gpu_device[VGPU_DEVICE_NAME_STR],
                                }
                            ]
                        },
                    }
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


def fetch_gpu_device_name_from_vm_instance(vm):
    devices = vm.vmi.instance.spec.domain.devices
    if devices.get("gpus") and devices.gpus:
        return devices.gpus[0].deviceName
    elif devices.get("hostDevices") and devices.hostDevices:
        return devices.hostDevices[0].deviceName
    else:
        raise ValueError(f"No GPU devices found in VM {vm.name}")


def get_num_gpu_devices_in_rhel_vm(vm):
    return int(
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=[
                "bash",
                "-c",
                '/sbin/lspci -nnk | grep -E "controller.+NVIDIA" | wc -l',
            ],
            wait_timeout=TIMEOUT_2MIN,
        )[0].strip()
    )


def get_gpu_device_name_from_windows_vm(vm):
    return run_ssh_commands(
        host=vm.ssh_exec,
        commands=[shlex.split("wmic path win32_VideoController get name")],
        tcp_timeout=TCP_TIMEOUT_30SEC,
        wait_timeout=TIMEOUT_2MIN,
    )[0]


def verify_gpu_device_exists_on_node(gpu_nodes, device_name):
    device_exists_failed_checks = []
    for gpu_node in gpu_nodes:
        for status_type in ["allocatable", "capacity"]:
            resources = getattr(gpu_node.instance.status, status_type).keys()
            if device_name not in resources:
                device_exists_failed_checks.append({
                    gpu_node.name: {
                        f"device_{status_type}": {
                            "expected": device_name,
                            "actual": resources,
                        }
                    }
                })
    assert not device_exists_failed_checks, f"Failed checks: {device_exists_failed_checks}"


def verify_gpu_device_exists_in_vm(vm, supported_gpu_device):
    if vm.os_flavor.startswith(OS_FLAVOR_WINDOWS):
        expected_gpu_name = (
            supported_gpu_device[VGPU_PRETTY_NAME_STR]
            if "vgpu" in vm.name
            else supported_gpu_device[GPU_PRETTY_NAME_STR]
        )
        assert expected_gpu_name in get_gpu_device_name_from_windows_vm(vm=vm), (
            f"GPU device {expected_gpu_name} does not exist in windows vm {vm.name}"
        )
    else:
        assert get_num_gpu_devices_in_rhel_vm(vm=vm) == 1, (
            f"GPU device {fetch_gpu_device_name_from_vm_instance(vm=vm)} does not exist in rhel vm {vm.name}"
        )


def get_allocatable_memory_per_node(schedulable_nodes):
    """
    Gets allocatable memory for each schedulable node.

    A node's allocatable memory is preferred, but if it's not set,
    the capacity value is used as a fallback.

    Args:
        schedulable_nodes (list): List of node objects`.

    Returns:
        dict: A dictionary mapping each node to its allocatable memory.
    """
    nodes_memory = {}
    for node in schedulable_nodes:
        # memory format does not include the Bytes suffix(e.g: 23514144Ki)
        memory = getattr(
            node.instance.status.allocatable,
            "memory",
            node.instance.status.capacity.memory,
        )
        nodes_memory[node] = bitmath.parse_string_unsafe(s=memory).to_KiB()
        LOGGER.info(f"Node {node.name} has {nodes_memory[node].to_GiB()} of allocatable memory")
    return nodes_memory


def assert_migration_post_copy_mode(vm):
    migration_state = vm.vmi.instance.status.migrationState
    assert migration_state.mode == "PostCopy", f"Migration mode is not PostCopy! VMI MigrationState {migration_state}"


def build_node_affinity_dict(values, key=None):
    return {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [
                    {
                        "matchExpressions": [
                            {
                                "key": key or f"{Resource.ApiGroup.KUBERNETES_IO}/hostname",
                                "operator": "In",
                                "values": values,
                            }
                        ]
                    }
                ]
            },
        }
    }


def get_pod_memory_requests(pod_instance):
    """Sum all memory requests of the pod's containers"""
    memory_requests = bitmath.Byte(value=0)
    for container in pod_instance.spec.containers:
        if hasattr(container.resources.requests, "memory"):
            memory_requests += bitmath.parse_string_unsafe(s=container.resources.requests.memory).to_KiB()
    return memory_requests


def get_non_terminated_pods(client, node):
    return list(
        Pod.get(
            client=client,
            field_selector=f"spec.nodeName={node.name},status.phase!=Succeeded,status.phase!=Failed",
        )
    )


def get_pci_addresses(vm: VirtualMachineForTests) -> list[str]:
    """Get sorted PCI device lines visible to the guest.

    Each line pairs a BDF address with its device description, enabling
    detection of both address shifts and device swaps on failure.

    Args:
        vm: Running VM with SSH access.

    Returns:
        Sorted list of lspci lines (e.g. ["00:01.0 Display controller: ..."]).
    """
    output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=["lspci"],
    )[0].strip()
    addresses = output.splitlines()
    LOGGER.info(f"PCI addresses for VM {vm.name}: {addresses}")
    return addresses


def get_boot_time_for_multiple_vms(vm_list):
    return {vm.name: get_vm_boot_time(vm=vm) for vm in vm_list}


def verify_guest_boot_time(vm_list, initial_boot_time):
    rebooted_vms = {}
    for vm in vm_list:
        current_boot_time = get_vm_boot_time(vm=vm)
        if initial_boot_time[vm.name] != current_boot_time:
            rebooted_vms[vm.name] = {"initial": initial_boot_time[vm.name], "current": current_boot_time}
    assert not rebooted_vms, f"Boot time changed for VMs:\n {rebooted_vms}"


def update_hco_memory_overcommit(admin_client, hco, percentage):
    with ResourceEditorValidateHCOReconcile(
        admin_client=admin_client,
        patches={
            hco: {
                "spec": {
                    "virtualization": {
                        "higherWorkloadDensity": {"memoryOvercommitPercentage": percentage},
                    }
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield
