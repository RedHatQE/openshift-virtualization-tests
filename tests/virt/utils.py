from __future__ import annotations

import logging
import re
import shlex
from contextlib import contextmanager

import bitmath
from kubernetes.dynamic.exceptions import NotFoundError, ResourceNotFoundError
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.constants import VIRT_PROCESS_MEMORY_LIMITS
from tests.virt.node.gpu.constants import (
    GPU_PRETTY_NAME_STR,
    MDEV_NAME_STR,
    MDEV_TYPE_STR,
    VGPU_DEVICE_NAME_STR,
    VGPU_PRETTY_NAME_STR,
)
from utilities.constants import (
    DEFAULT_HCO_CONDITIONS,
    OS_FLAVOR_WINDOWS,
    OS_PROC_NAME,
    TCP_TIMEOUT_30SEC,
    TIMEOUT_1MIN,
    TIMEOUT_1SEC,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_15SEC,
    TIMEOUT_30SEC,
)
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    is_hco_tainted,
    update_hco_annotations,
    wait_for_hco_conditions,
)
from utilities.infra import ExecCommandOnPod, get_pod_by_name_prefix
from utilities.virt import (
    VirtualMachineForTests,
    fetch_pid_from_linux_vm,
    fetch_pid_from_windows_vm,
    kill_processes_by_name_linux,
    migrate_vm_and_verify,
    pause_optional_migrate_unpause_and_check_connectivity,
    start_and_fetch_processid_on_linux_vm,
    start_and_fetch_processid_on_windows_vm,
    verify_vm_migrated,
    wait_for_migration_finished,
    wait_for_updated_kv_value,
)

LOGGER = logging.getLogger(__name__)


@contextmanager
def append_feature_gate_to_hco(feature_gate, resource, client, namespace):
    with update_hco_annotations(
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
                **{"TaintedConfiguration": Resource.Condition.Status.TRUE},
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


def get_virt_launcher_processes_memory_overuse(pod):
    memory_overuse = {}
    for process in VIRT_PROCESS_MEMORY_LIMITS.keys():
        memory_usage = bitmath.KiB(
            value=int(
                pod.execute(
                    command=shlex.split(f"bash -c 'ps -o rss --no-headers -p $(pidof {process})'"),
                    container="compute",
                )
            )
        )
        if memory_usage > VIRT_PROCESS_MEMORY_LIMITS[process]:
            memory_overuse[process] = {
                "memory usage": memory_usage,
                "memory limit": VIRT_PROCESS_MEMORY_LIMITS[process],
            }
    return memory_overuse


def get_stress_ng_pid(ssh_exec, windows=False):
    stress = "stress-ng"
    LOGGER.info(f"Get pid of {stress}")
    command_prefix = "wsl" if windows else ""

    return run_ssh_commands(
        host=ssh_exec,
        commands=shlex.split(f"{command_prefix} bash -c 'pgrep {stress}'"),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )[0].split("\n")[0]


def verify_stress_ng_pid_not_changed(vm, initial_pid, windows=False):
    current_stress_ng_pid = get_stress_ng_pid(
        ssh_exec=vm.ssh_exec,
        windows=windows,
    )
    assert initial_pid == current_stress_ng_pid, (
        f"stress-ng pid changed. Before: {initial_pid}. Current: {current_stress_ng_pid}"
    )


def verify_wsl2_guest_running(vm, timeout=TIMEOUT_3MIN):
    def _get_wsl2_running_status():
        guests_status = run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split("powershell.exe -command wsl -l -v"),
            tcp_timeout=TCP_TIMEOUT_30SEC,
        )[0]
        guests_status = guests_status.replace("\x00", "")
        LOGGER.info(guests_status)
        return re.search(r".*(Running).*\n", guests_status) is not None

    sampler = TimeoutSampler(wait_timeout=timeout, sleep=TIMEOUT_5SEC, func=_get_wsl2_running_status)
    try:
        for sample in sampler:
            if sample:
                return True
    except TimeoutExpiredError:
        LOGGER.error("WSL2 guest is not running in the VM!")
        raise


def verify_wsl2_guest_works(vm: VirtualMachineForTests) -> None:
    """
    Verifies that WSL2 is functioning on windows vm.
    Args:
        vm: An instance of `VirtualMachineForTests`
    Raises:
        TimeoutExpiredError: If WSL2 fails to return the expected output within
            the specified timeout period.
    """
    echo_string = "TEST"
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_15SEC,
        func=run_ssh_commands,
        host=vm.ssh_exec,
        commands=shlex.split(f"wsl echo {echo_string}"),
    )
    try:
        for sample in samples:
            if sample and echo_string in sample[0]:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"VM {vm.name} failed to start WSL2")
        raise


def start_stress_on_vm(vm, stress_command):
    LOGGER.info(f"Running memory load in VM {vm.name}")
    if "windows" in vm.name:
        verify_wsl2_guest_running(vm=vm)
        verify_wsl2_guest_works(vm=vm)
        command = f"wsl nohup bash -c '{stress_command}'"
    else:
        command = stress_command
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(command),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )


def migrate_and_verify_multi_vms(vm_list):
    vms_dict = {}
    failed_migrations_list = []

    for vm in vm_list:
        vms_dict[vm.name] = {
            "node_before": vm.vmi.node,
            "vm_mig": migrate_vm_and_verify(vm=vm, wait_for_migration_success=False),
        }

    for vm in vm_list:
        migration = vms_dict[vm.name]["vm_mig"]
        wait_for_migration_finished(vm=vm, migration=migration)
        migration.clean_up()

    for vm in vm_list:
        vm_sources = vms_dict[vm.name]
        try:
            verify_vm_migrated(vm=vm, node_before=vm_sources["node_before"])
        except (AssertionError, TimeoutExpiredError):
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


@contextmanager
def enable_aaq_in_hco(client, hco_namespace, hyperconverged_resource, enable_acrq_support=False):
    patches = {hyperconverged_resource: {"spec": {"enableApplicationAwareQuota": True}}}
    if enable_acrq_support:
        patches[hyperconverged_resource]["spec"]["applicationAwareConfig"] = {
            "allowApplicationAwareClusterResourceQuota": True
        }

    with ResourceEditorValidateHCOReconcile(
        patches=patches,
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield
    # need to wait when all AAQ system pods removed
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=get_pod_by_name_prefix,
        dyn_client=client,
        pod_prefix="aaq-(controller|server)",
        namespace=hco_namespace.name,
        get_all=True,
    )
    sample = None
    try:
        for sample in samples:
            if not sample:
                break
    except TimeoutExpiredError:
        LOGGER.error(f"Some AAQ pods still present: {sample}")
        raise
    except (NotFoundError, ResourceNotFoundError):
        LOGGER.info("AAQ system PODs removed.")


def kill_processes_by_name_windows(vm, process_name):
    cmd = shlex.split(f"taskkill /F /IM {process_name}")
    run_ssh_commands(host=vm.ssh_exec, commands=cmd, tcp_timeout=TCP_TIMEOUT_30SEC)


def validate_pause_optional_migrate_unpause_windows_vm(vm, pre_pause_pid=None, migrate=False):
    proc_name = OS_PROC_NAME["windows"]
    if not pre_pause_pid:
        pre_pause_pid = start_and_fetch_processid_on_windows_vm(vm=vm, process_name=proc_name)
    pause_optional_migrate_unpause_and_check_connectivity(vm=vm, migrate=migrate)
    post_pause_pid = fetch_pid_from_windows_vm(vm=vm, process_name=proc_name)
    kill_processes_by_name_windows(vm=vm, process_name=proc_name)
    assert post_pause_pid == pre_pause_pid, (
        f"PID mismatch!\nPre pause PID is: {pre_pause_pid}\nPost pause PID is: {post_pause_pid}"
    )


def get_match_expressions_dict(nodes_list):
    return {
        "matchExpressions": [
            {
                "key": f"{Resource.ApiGroup.KUBERNETES_IO}/hostname",
                "operator": "In",
                "values": nodes_list,
            }
        ]
    }


def wait_for_virt_launcher_pod(vmi):
    samples = TimeoutSampler(wait_timeout=TIMEOUT_30SEC, sleep=TIMEOUT_1SEC, func=lambda: vmi.virt_launcher_pod)
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Virt-laucher pod for VMI {vmi.name} was not found!")
        raise


def validate_machine_type(
    vm, expected_machine_type, expected_libvirt_machine_type=None
):  # Incase of s390x machine_type in VM/VMI are different than one in libvirt xml
    vm_machine_type = vm.instance.spec.template.spec.domain.machine.type
    vmi_machine_type = vm.vmi.instance.spec.domain.machine.type
    if expected_libvirt_machine_type is None:
        expected_libvirt_machine_type = expected_machine_type

    assert vm_machine_type == vmi_machine_type == expected_machine_type, (
        "Created VM's machine type does not match the request. "
        f"Expected: {expected_machine_type} VM: {vm_machine_type}, VMI: {vmi_machine_type}"
    )
    vmi_xml_machine_type = vm.privileged_vmi.xml_dict["domain"]["os"]["type"]["@machine"]
    assert vmi_xml_machine_type == expected_libvirt_machine_type, (
        f"libvirt machine type {vmi_xml_machine_type} does not match expected type {expected_libvirt_machine_type}"
    )


def patch_hco_cr_with_mdev_permitted_hostdevices(hyperconverged_resource, supported_gpu_device):
    required_keys = [MDEV_TYPE_STR, MDEV_NAME_STR, VGPU_DEVICE_NAME_STR]
    missing_keys = [key for key in required_keys if key not in supported_gpu_device]
    if missing_keys:
        raise ValueError(f"Missing required keys in supported_gpu_device: {missing_keys}")
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource: {
                "spec": {
                    "mediatedDevicesConfiguration": {"mediatedDeviceTypes": [supported_gpu_device[MDEV_TYPE_STR]]},
                    "permittedHostDevices": {
                        "mediatedDevices": [
                            {
                                "mdevNameSelector": supported_gpu_device[MDEV_NAME_STR],
                                "resourceName": supported_gpu_device[VGPU_DEVICE_NAME_STR],
                            }
                        ]
                    },
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
        )[0].strip()
    )


def get_gpu_device_name_from_windows_vm(vm):
    return run_ssh_commands(
        host=vm.ssh_exec,
        commands=[shlex.split("wmic path win32_VideoController get name")],
        tcp_timeout=TCP_TIMEOUT_30SEC,
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


def check_node_for_missing_mdev_bus(node_and_shared_list):
    node, shared_list, workers_utility_pods = node_and_shared_list
    pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=TIMEOUT_5SEC,
            func=pod_exec.exec,
            command="ls /sys/class | grep mdev_bus || true",
        ):
            if sample:
                return
    except TimeoutExpiredError:
        shared_list.append(node.name)
