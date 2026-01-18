from __future__ import annotations

import logging
import shlex
from contextlib import contextmanager
from typing import Any, Generator

import bitmath
from kubernetes.dynamic import DynamicClient
from ocp_resources.data_source import DataSource
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.gpu.constants import (
    GPU_PRETTY_NAME_STR,
    MDEV_NAME_STR,
    MDEV_TYPE_STR,
    VGPU_DEVICE_NAME_STR,
    VGPU_PRETTY_NAME_STR,
)
from utilities.artifactory import get_test_artifact_server_url
from utilities.constants import (
    DATA_SOURCE_STR,
    DEFAULT_HCO_CONDITIONS,
    OS_FLAVOR_WINDOWS,
    OS_PROC_NAME,
    TCP_TIMEOUT_30SEC,
    TIMEOUT_1SEC,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
    TIMEOUT_30MIN,
    TIMEOUT_30SEC,
)
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    is_hco_tainted,
    update_hco_annotations,
    wait_for_hco_conditions,
)
from utilities.storage import (
    create_dv,
    create_or_update_data_source,
    data_volume_template_with_source_ref_dict,
    get_storage_class_dict_from_matrix,
)
from utilities.virt import (
    VirtualMachineForTests,
    fetch_pid_from_linux_vm,
    fetch_pid_from_windows_vm,
    get_vm_boot_time,
    kill_processes_by_name_linux,
    migrate_vm_and_verify,
    pause_unpause_vm_and_check_connectivity,
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
        wait_for_migration_finished(namespace=vm.namespace, migration=migration)
        migration.clean_up()

    for vm in vm_list:
        vm_sources = vms_dict[vm.name]
        try:
            verify_vm_migrated(vm=vm, node_before=vm_sources["node_before"])
        except AssertionError | TimeoutExpiredError:
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


def kill_processes_by_name_windows(vm, process_name):
    cmd = shlex.split(f"taskkill /F /IM {process_name}")
    run_ssh_commands(host=vm.ssh_exec, commands=cmd, tcp_timeout=TCP_TIMEOUT_30SEC)


def validate_pause_unpause_windows_vm(vm: VirtualMachineForTests, pre_pause_pid: int | None = None) -> None:
    proc_name = OS_PROC_NAME["windows"]
    if not pre_pause_pid:
        pre_pause_pid = start_and_fetch_processid_on_windows_vm(vm=vm, process_name=proc_name)
    pause_unpause_vm_and_check_connectivity(vm=vm)
    post_pause_pid = fetch_pid_from_windows_vm(vm=vm, process_name=proc_name)
    kill_processes_by_name_windows(vm=vm, process_name=proc_name)
    assert post_pause_pid == pre_pause_pid, (
        f"PID mismatch!\nPre pause PID is: {pre_pause_pid}\nPost pause PID is: {post_pause_pid}"
    )


def wait_for_virt_launcher_pod(vmi):
    samples = TimeoutSampler(wait_timeout=TIMEOUT_30SEC, sleep=TIMEOUT_1SEC, func=lambda: vmi.virt_launcher_pod)
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Virt-laucher pod for VMI {vmi.name} was not found!")
        raise


def validate_machine_type(vm, expected_machine_type):
    vm_machine_type = vm.instance.spec.template.spec.domain.machine.type
    vmi_machine_type = vm.vmi.instance.spec.domain.machine.type

    assert vm_machine_type == vmi_machine_type == expected_machine_type, (
        "Created VM's machine type does not match the request. "
        f"Expected: {expected_machine_type} VM: {vm_machine_type}, VMI: {vmi_machine_type}"
    )
    vmi_xml_machine_type = vm.privileged_vmi.xml_dict["domain"]["os"]["type"]["@machine"]
    assert vmi_xml_machine_type == expected_machine_type, (
        f"libvirt machine type {vmi_xml_machine_type} does not match expected type {expected_machine_type}"
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


def get_boot_time_for_multiple_vms(vm_list):
    return {vm.name: get_vm_boot_time(vm=vm) for vm in vm_list}


def verify_guest_boot_time(vm_list, initial_boot_time):
    rebooted_vms = {}
    for vm in vm_list:
        current_boot_time = get_vm_boot_time(vm=vm)
        if initial_boot_time[vm.name] != current_boot_time:
            rebooted_vms[vm.name] = {"initial": initial_boot_time[vm.name], "current": current_boot_time}
    assert not rebooted_vms, f"Boot time changed for VMs:\n {rebooted_vms}"


def get_or_create_golden_image_data_source(
    admin_client: DynamicClient, golden_images_namespace: Namespace, os_dict: dict[str, Any]
) -> Generator[DataSource, None, None]:
    """Retrieves or creates a DataSource object in golden image namespace specified in the OS matrix.

    Args:
        admin_client (DynamicClient): Kubernetes dynamic client.
        golden_images_namespace (Namespace): Namespace where golden images are stored.
        os_dict (dict[str, Any]): dict of os params

    Yields:
        DataSource: DataSource object.
    """

    data_source_name = os_dict.get(DATA_SOURCE_STR, "dummy")

    data_source = DataSource(client=admin_client, name=data_source_name, namespace=golden_images_namespace.name)
    if data_source.exists and data_source.source.exists:
        LOGGER.info(f"DataSource {data_source_name} already exists and has a source pvc/snapshot.")
        yield data_source
    else:
        LOGGER.warning(f"No DataSource {data_source_name} found or it doesn't have a source pvc/snapshot.")

        with create_dv(
            dv_name=data_source_name,
            namespace=golden_images_namespace.name,
            storage_class=py_config["default_storage_class"],
            url=f"{get_test_artifact_server_url()}{os_dict['image_path']}",
            size=os_dict["dv_size"],
            client=admin_client,
        ) as dv:
            dv.wait_for_dv_success(timeout=TIMEOUT_30MIN)
            yield from create_or_update_data_source(admin_client=admin_client, dv=dv)


def get_data_volume_template_dict_with_default_storage_class(
    data_source: DataSource, storage_class: str | None = None
) -> dict[str, dict]:
    """
    Generates a dataVolumeTemplate dict with the py_config based storage class.

    Args:
        data_source (DataSource): The data source object used to create the data volume template.
        storage_class (str, optional): Storage class name.

    Returns:
        dict[str, dict]: A dict representing the dataVolumeTemplate to be used in VM spec.
    """
    data_volume_template = data_volume_template_with_source_ref_dict(data_source=data_source)

    # access modes is needed to correctly set eviction strategy in VMs from template
    # (see to_dict method in VirtualMachineForTestsFromTemplate class)
    # TODO: remove access modes after the logic in VirtualMachineForTestsFromTemplate is updated
    if storage_class:
        data_volume_template["spec"]["storage"]["storageClassName"] = storage_class
        data_volume_template["spec"]["storage"]["accessModes"] = [
            get_storage_class_dict_from_matrix(storage_class=storage_class)[storage_class]["access_mode"]
        ]
    else:
        data_volume_template["spec"]["storage"]["storageClassName"] = py_config["default_storage_class"]
        data_volume_template["spec"]["storage"]["accessModes"] = [py_config["default_access_mode"]]
    return data_volume_template


def update_hco_memory_overcommit(hco, percentage):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hco: {
                "spec": {
                    "higherWorkloadDensity": {"memoryOvercommitPercentage": percentage},
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield
