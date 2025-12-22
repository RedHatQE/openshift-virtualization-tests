import logging
import math
import re
import shlex
import time
import urllib
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional

import bitmath
from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_utilities.monitoring import Prometheus
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.constants import KUBEVIRT_VIRT_OPERATOR_READY
from tests.observability.metrics.constants import (
    BINDING_NAME,
    BINDING_TYPE,
    GO_VERSION_STR,
    KUBE_VERSION_STR,
    KUBEVIRT_VMI_FILESYSTEM_BYTES,
    KUBEVIRT_VMI_FILESYSTEM_BYTES_WITH_MOUNT_POINT,
)
from tests.observability.utils import validate_metrics_value
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_http_image_url,
)
from utilities.constants import (
    CAPACITY,
    KUBEVIRT_VIRT_OPERATOR_UP,
    NODE_STR,
    OS_FLAVOR_WINDOWS,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_4MIN,
    TIMEOUT_5MIN,
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
    TIMEOUT_20SEC,
    TIMEOUT_30SEC,
    USED,
    VIRT_HANDLER,
    Images,
)
from utilities.monitoring import get_metrics_value
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)
CURL_QUERY = "curl -k https://localhost:8443/metrics"
SINGLE_VM = 1
COUNT_THREE = 3


def get_vm_metrics(prometheus: Prometheus, query: str, vm_name: str, timeout: int = TIMEOUT_5MIN) -> list[dict] | None:
    """
    Performs Prometheus query, waits for the expected vm related metrics to show up in results,
    returns the query results

    Args:
        prometheus(Prometheus Object): Prometheus object.
        query(str): Prometheus query string (for strings with special characters they need to be parsed by the
        caller)
        vm_name(str): name of the vm to look for in prometheus query results
        timeout(int): Timeout value in seconds

    Returns:
        list: List of query results if appropriate vm name is found in the results.

    Raise:
        TimeoutExpiredError: if a given vm name does not show up in prometheus query results

    """
    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=5,
        func=prometheus.query_sampler,
        query=query,
    )
    sample = None
    try:
        for sample in sampler:
            if sample and vm_name in [name.get("metric").get("name") for name in sample]:
                return sample
    except TimeoutExpiredError:
        LOGGER.error(f'vm {vm_name} not found via prometheus query: "{query}" result: {sample}')
        raise
    return None


def assert_vm_metric(prometheus: Prometheus, query: str, vm_name: str):
    assert get_vm_metrics(prometheus=prometheus, query=query, vm_name=vm_name), (
        f"query: {query} has no result for vm: {vm_name}"
    )


def parse_vm_metric_results(raw_output: str) -> dict[str, Any]:
    """
    Parse metrics received from virt-handler pod

    Args:
        raw_output (str): raw metric output received from virt-handler pods

    Returns:
        dict: Dictionary of parsed output
    """
    regex_metrics = r"(?P<metric>\S+)\{(?P<labels>[^\}]+)\}[ ](?P<value>\d+)"
    metric_results: dict[str, Any] = {}
    for line in raw_output.splitlines():
        if line.startswith("# HELP"):
            metric, description = line[7:].split(" ", 1)
            metric_results.setdefault(metric, {})["help"] = description
        elif line.startswith("# TYPE"):
            metric, metric_type = line[7:].split(" ", 1)
            metric_results.setdefault(metric, {})["type"] = metric_type
        elif re.match(regex_metrics, line):
            match = re.match(regex_metrics, line)
            if match:
                metric_instance_dict = match.groupdict()
                metric_instance_dict["labeldict"] = {
                    val[0]: val[-1]
                    for val in [label.partition("=") for label in metric_instance_dict["labels"].split(",")]
                }
                metric_results.setdefault(metric_instance_dict["metric"], {}).setdefault("results", []).append(
                    metric_instance_dict
                )
        else:
            metric, metric_type = line.split(" ", 1)
            metric_results.setdefault(metric, {})["type"] = metric_type
    return metric_results


def assert_vm_metric_virt_handler_pod(query: str, vm: VirtualMachineForTests):
    """
    Get vm metric information from virt-handler pod

    Args:
        query (str): Prometheus query string
        vm (VirtualMachineForTests): A VirtualMachineForTests

    """
    pod = vm.privileged_vmi.virt_handler_pod
    output = parse_vm_metric_results(raw_output=pod.execute(command=["bash", "-c", f"{CURL_QUERY}"]))
    assert output, f'No query output found from {VIRT_HANDLER} pod "{pod.name}" for query: "{CURL_QUERY}"'
    metrics_list = []
    if query in output:
        metrics_list = [
            result["labeldict"]
            for result in output[query]["results"]
            if "labeldict" in result and vm.name in result["labeldict"]["name"]
        ]
    assert metrics_list, (
        f'{VIRT_HANDLER} pod query:"{CURL_QUERY}" did not return any vm metric information for vm: {vm.name} '
        f"from {VIRT_HANDLER} pod: {pod.name}. "
    )
    assert_validate_vm_metric(vm=vm, metrics_list=metrics_list)


def assert_validate_vm_metric(vm: VirtualMachineForTests, metrics_list: list[dict[str, str]]) -> None:
    """
    Validate vm metric information fetched from virt-handler pod

    Args:
        vm (VirtualMachineForTests): A VirtualMachineForTests
        metrics_list (list): List of metrics entries collected from associated Virt-handler pod

    """
    expected_values = {
        "kubernetes_vmi_label_kubevirt_io_nodeName": vm.vmi.node.name,
        "namespace": vm.namespace,
        "node": vm.vmi.node.name,
    }
    LOGGER.info(f"{VIRT_HANDLER} pod metrics associated with vm: {vm.name} are: {metrics_list}")
    metric_data_mismatch = [
        entity
        for key in expected_values
        for entity in metrics_list
        if not entity.get(key, None) or expected_values[key] not in entity[key]
    ]

    assert not metric_data_mismatch, (
        f"Vm metric validation via {VIRT_HANDLER} pod {vm.vmi.virt_handler_pod} failed: {metric_data_mismatch}"
    )


def is_swap_enabled(vm: VirtualMachineForTests, swap_name: str = r"\/dev\/zram0") -> bool:
    out = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("swapon --raw"))
    LOGGER.info(f"Swap: {out}")
    if not out:
        return False
    return bool(re.findall(f"{swap_name}", "".join(out)))


def enable_swap_fedora_vm(vm: VirtualMachineForTests) -> None:
    """
    Enable swap on on fedora vms

    Args:
       vm (VirtualMachineForTests): a VirtualMachineForTests, on which swap is to be enabled

    Raise:
        Asserts if swap memory is not enabled on a given vm
    """
    if not is_swap_enabled(vm=vm):
        swap_name = "myswap"
        for command in [
            f"dd if=/dev/zero of=/{swap_name} bs=1M count=1000",
            f"chmod 600 /{swap_name}",
            f"mkswap /{swap_name}",
            f"swapon /{swap_name}",
        ]:
            vm.ssh_exec.executor(sudo=True).run_cmd(cmd=shlex.split(command))

        assert is_swap_enabled(vm=vm, swap_name=swap_name), f"Failed to enable swap memory {swap_name} on {vm.name}"
    vm.ssh_exec.executor(sudo=True).run_cmd(cmd=shlex.split("sysctl vm.swappiness=100"))


def get_vm_cpu_info_from_prometheus(prometheus: Prometheus, vm_name: str) -> Optional[int]:
    query = urllib.parse.quote_plus(
        f'kubevirt_vmi_node_cpu_affinity{{kubernetes_vmi_label_kubevirt_io_domain="{vm_name}"}}'
    )
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=2,
        func=prometheus.query_sampler,
        query=query,
    )
    sample = None
    try:
        for sample in samples:
            if sample:
                return int(sample[0]["value"][1])
    except TimeoutExpiredError:
        LOGGER.error(f"Failed to get data from query '{query}' in time. Current data: {sample}")
        raise
    return None


def validate_vmi_node_cpu_affinity_with_prometheus(prometheus: Prometheus, vm: VirtualMachineForTests) -> None:
    vm_cpu = vm.vmi.instance.spec.domain.cpu
    cpu_count_from_vm = (vm_cpu.threads or 1) * (vm_cpu.cores or 1) * (vm_cpu.sockets or 1)
    LOGGER.info(f"Cpu count from vm {vm.name}: {cpu_count_from_vm}")
    cpu_info_from_prometheus = get_vm_cpu_info_from_prometheus(prometheus=prometheus, vm_name=vm.name)
    LOGGER.info(f"CPU information from prometheus: {cpu_info_from_prometheus}")
    cpu_count_from_vm_node = int(vm.privileged_vmi.node.instance.status.capacity.cpu)
    LOGGER.info(f"Cpu count from node {vm.privileged_vmi.node.name}: {cpu_count_from_vm_node}")

    if cpu_count_from_vm > 1:
        cpu_count_from_vm_node = cpu_count_from_vm_node * cpu_count_from_vm

    assert cpu_count_from_vm_node == cpu_info_from_prometheus, (
        f"Actual CPU count {cpu_count_from_vm_node} not matching with "
        f"expected CPU count {cpu_info_from_prometheus} for VM CPU {cpu_count_from_vm}"
    )


def get_resource_object(
    admin_client: DynamicClient, related_objects: list, resource_kind, resource_name: str
) -> Resource | None:
    for related_obj in related_objects:
        if resource_kind.__name__ == related_obj["kind"]:
            namespace = related_obj.get("namespace")
            if namespace:
                return resource_kind(
                    client=admin_client,
                    name=resource_name,
                    namespace=namespace,
                )
            return resource_kind(
                client=admin_client,
                name=resource_name,
            )

    return None


def assert_virtctl_version_equal_metric_output(
    virtctl_server_version: dict[str, str], metric_output: list[dict[str, dict[str, str]]]
) -> None:
    mismatch_result = []
    metric_result = None
    for virt_handler_pod_metrics in metric_output:
        metric_result = virt_handler_pod_metrics.get("metric")
        if metric_result:
            if (
                metric_result[KUBE_VERSION_STR] != virtctl_server_version[KUBE_VERSION_STR]
                or metric_result[GO_VERSION_STR] != virtctl_server_version[GO_VERSION_STR]
            ):
                mismatch_result.append(metric_result)
    assert not mismatch_result, (
        f"Data mismatch, expected version results:{virtctl_server_version}\nactual results {metric_result}"
    )


def validate_metric_value_within_range(
    prometheus: Prometheus, metric_name: str, expected_value: float, timeout: int = TIMEOUT_4MIN
) -> None:
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_15SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=metric_name,
    )
    sample: int | float = 0
    try:
        for sample in samples:
            if sample:
                sample = abs(float(sample))
                if sample * 0.95 <= abs(expected_value) <= sample * 1.05:
                    return
    except TimeoutExpiredError:
        LOGGER.info(
            f"Metric value of: {metric_name} is: {sample}, expected value:{expected_value},\n "
            f"The value should be between: {sample * 0.95}-{sample * 1.05}"
        )
        raise


def network_packets_received(vm: VirtualMachineForTests, interface_name: str) -> dict[str, str]:
    ip_link_show_content = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("ip -s link show"))[0]
    pattern = re.compile(
        rf".*?{re.escape(interface_name)}:.*?"  # Match the line with the interface name
        r"(?:RX:\s+bytes\s+packets\s+errors\s+dropped\s+.*?(\d+)\s+(\d+)\s+(\d+)\s+(\d+)).*?"  # Capture RX stats
        r"(?:TX:\s+bytes\s+packets\s+errors\s+dropped\s+.*?(\d+)\s+(\d+)\s+(\d+)\s+(\d+))",  # Capture TX stats
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(string=ip_link_show_content)
    if match:
        rx_bytes, rx_packets, rx_errs, rx_drop, tx_bytes, tx_packets, tx_errs, tx_drop = match.groups()
        return {
            "rx_bytes": rx_bytes,
            "rx_packets": rx_packets,
            "rx_errs": rx_errs,
            "rx_drop": rx_drop,
            "tx_bytes": tx_bytes,
            "tx_packets": tx_packets,
            "tx_errs": tx_errs,
            "tx_drop": tx_drop,
        }
    return {}


def compare_network_traffic_bytes_and_metrics(
    prometheus: Prometheus, vm: VirtualMachineForTests, vm_interface_name: str
) -> bool:
    packet_received = network_packets_received(vm=vm, interface_name=vm_interface_name)
    rx_tx_indicator = False
    LOGGER.info("Waiting for metric kubevirt_vmi_network_traffic_bytes_total to update")
    time.sleep(TIMEOUT_15SEC)
    metric_result = (
        prometheus.query(query=f"kubevirt_vmi_network_traffic_bytes_total{{name='{vm.name}'}}")
        .get("data")
        .get("result")
    )
    for entry in metric_result:
        entry_value = entry.get("value")[1]
        if math.isclose(
            int(entry_value), int(packet_received[f"{entry.get('metric').get('type')}_bytes"]), rel_tol=0.05
        ):
            rx_tx_indicator = True
        else:
            break
    if rx_tx_indicator:
        return True
    return False


def validate_network_traffic_metrics_value(
    prometheus: Prometheus, vm: VirtualMachineForTests, interface_name: str
) -> None:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_4MIN,
        sleep=TIMEOUT_10SEC,
        func=compare_network_traffic_bytes_and_metrics,
        prometheus=prometheus,
        vm=vm,
        vm_interface_name=interface_name,
    )
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error("Metric value and domistat value not correlate.")
        raise


def get_metric_sum_value(prometheus: Prometheus, metric: str) -> int:
    metrics = prometheus.query(query=metric)
    metrics_result = metrics["data"].get("result", [])
    if metrics_result:
        return sum(int(metric_metrics_result["value"][1]) for metric_metrics_result in metrics_result)
    LOGGER.warning(f"For Query {metric}, empty results found.")
    return 0


def wait_for_expected_metric_value_sum(
    prometheus: Prometheus,
    metric_name: str,
    expected_value: int,
    check_times: int = 3,
    timeout: int = TIMEOUT_4MIN,
) -> None:
    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_15SEC,
        func=get_metric_sum_value,
        prometheus=prometheus,
        metric=metric_name,
    )
    sample = None
    current_check = 0
    comparison_values_log = {}
    try:
        for sample in sampler:
            if sample:
                comparison_values_log[datetime.now()] = (
                    f"metric: {metric_name} value is: {sample}, the expected value is {expected_value}"
                )
            if sample == expected_value:
                current_check += 1
                if current_check >= check_times:
                    return
            else:
                current_check = 0

    except TimeoutExpiredError:
        LOGGER.error(
            f"Metric: {metric_name}, metrics value: {sample}, expected: {expected_value}, "
            f"comparison log: {comparison_values_log}"
        )
        raise


def metric_result_output_dict_by_mountpoint(
    prometheus: Prometheus, capacity_or_used: str, vm_name: str
) -> dict[str, str]:
    return {
        entry["metric"]["mount_point"]: entry["value"][1]
        for entry in prometheus.query(
            query=KUBEVIRT_VMI_FILESYSTEM_BYTES.format(capacity_or_used=capacity_or_used, vm_name=vm_name)
        )
        .get("data")
        .get("result")
    }


def compare_kubevirt_vmi_info_metric_with_vm_info(
    prometheus: Prometheus, query: str, expected_value: str, values_to_compare: dict
) -> None:
    """
    This function waiting of Prometheus query output to match expected value
    Args:
        prometheus (Prometheus): Prometheus object
        query (str): Prometheus query string
        expected_value (str): expected_value for the query
        values_to_compare (dict): entries with values from the vm to compare with prometheus

    """
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_20SEC,
        func=prometheus.query_sampler,
        query=query,
    )
    missing_entries = None
    metric_value_field = None
    values_mismatch = None
    expected_entries = values_to_compare.keys()
    try:
        for sample in sampler:
            if sample and sample[0].get("metric"):
                query_result = sample[0]
                metric_fields = query_result["metric"]
                metric_value_field = query_result.get("value")[1]
                missing_entries = [entry for entry in expected_entries if entry not in metric_fields]
                if not missing_entries:
                    values_mismatch = {
                        field_name: (
                            f"Value from vm: {vm_command_value}, value from prometheus query: "
                            f"{metric_fields.get(field_name)}"
                        )
                        for field_name, vm_command_value in values_to_compare.items()
                        if metric_fields.get(field_name) != vm_command_value
                    }
                    if metric_value_field == expected_value and not values_mismatch:
                        return
                missing_entries = None
    except TimeoutExpiredError:
        LOGGER.error(
            f"timeout exception waiting Prometheus query to match expected value: {expected_value}\n"
            f"query: {query}, results: {metric_value_field}\n"
            f"missing entries: {missing_entries}, expected entries: {expected_entries}\n"
            f"The following values has a mismatch between metric and vm values: {values_mismatch}\n"
        )
        raise


def validate_initial_virt_operator_replicas_reverted(
    prometheus: Prometheus, initial_virt_operator_replicas: str
) -> None:
    for metric in [KUBEVIRT_VIRT_OPERATOR_READY, KUBEVIRT_VIRT_OPERATOR_UP]:
        validate_metrics_value(
            prometheus=prometheus,
            expected_value=initial_virt_operator_replicas,
            metric_name=metric,
        )


def timestamp_to_seconds(timestamp: str) -> int:
    # Parse the timestamp with UTC timezone and convert to seconds
    dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    dt = dt.replace(tzinfo=timezone.utc)  # Ensure it is treated as UTC
    return int(dt.timestamp())


def wait_for_non_empty_metrics_value(prometheus: Prometheus, metric_name: str) -> None:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=metric_name,
    )
    sample = None
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.info(f"Metric value of: {metric_name} is: {sample}, expected value: non empty value.")
        raise


def disk_file_system_info(vm: VirtualMachineForTests) -> dict[str, dict[str, str]]:
    lines = re.findall(
        r"fs\.(\d+)\.(mountpoint|total-bytes|used-bytes)\s*:\s*(.*)\s*",
        vm.privileged_vmi.execute_virsh_command(command="guestinfo --filesystem"),
        re.MULTILINE,
    )
    mount_points_and_values_dict: dict[str, dict[str, str]] = {}
    for fs_id, label, value in lines:
        mount_points_and_values_dict.setdefault(fs_id, {})[label] = value
    file_system_info = {
        info["mountpoint"]: {USED: info["used-bytes"], CAPACITY: info["total-bytes"]}
        for info in mount_points_and_values_dict.values()
        if "used-bytes" in info and "total-bytes" in info
    }
    assert file_system_info, "No mountpoints found with value."
    return file_system_info


def compare_metric_file_system_values_with_vm_file_system_values(
    prometheus: Prometheus,
    vm_for_test: VirtualMachineForTests,
    mount_point: str,
    capacity_or_used: str,
) -> None:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_15SEC,
        func=disk_file_system_info,
        vm=vm_for_test,
    )
    sample = None
    metric_value = None
    try:
        for sample in samples:
            if sample:
                metric_value = float(
                    get_metrics_value(
                        prometheus=prometheus,
                        metrics_name=KUBEVIRT_VMI_FILESYSTEM_BYTES_WITH_MOUNT_POINT.format(
                            capacity_or_used=capacity_or_used,
                            vm_name=vm_for_test.name,
                            mountpoint=f"{mount_point}\\" if mount_point.endswith("\\") else mount_point,
                        ),
                    )
                )
                virsh_raw = sample[mount_point].get(capacity_or_used)
                virsh_bytes = float(virsh_raw if virsh_raw.isdigit() else bitmath.parse_string_unsafe(virsh_raw).bytes)
                if math.isclose(metric_value, virsh_bytes, rel_tol=0.05):
                    return
    except TimeoutExpiredError:
        LOGGER.info(
            f"Value for mount point: {mount_point} from virsh command: {sample}\n "
            f"Result from metric for the mountpoint: {mount_point}: {metric_value}"
        )
        raise


def expected_metric_labels_and_values(
    expected_labels_and_values: dict[str, str], values_from_prometheus: dict[str, str]
) -> None:
    mismatch = {
        label: {
            f"{label} metric result: {values_from_prometheus.get(label)}, "
            f"expected_label_results: {expected_label_results}"
        }
        for label, expected_label_results in expected_labels_and_values.items()
        if values_from_prometheus.get(label) != expected_label_results
    }
    assert not mismatch, f"There is a missmatch in expected values and metric result: {mismatch}"


def validate_metric_value_with_round_down(
    prometheus: Prometheus, metric_name: str, expected_value: float, timeout: int = TIMEOUT_4MIN
) -> None:
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_15SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=metric_name,
    )
    sample: int | float = 0
    try:
        for sample in samples:
            sample = round(float(sample))
            if sample and sample == abs(expected_value):
                return
    except TimeoutExpiredError:
        LOGGER.info(f"Metric int value of: {metric_name} is: {sample}, expected value:{expected_value}")
        raise


def binding_name_and_type_from_vm_or_vmi(vm_interface: dict[str, str]) -> dict[str, str]:
    binding_name_and_type = None
    for binding_name in ["masquerade", "bridge", "sriov"]:
        if vm_interface.get(binding_name):
            binding_name_and_type = {BINDING_NAME: binding_name, BINDING_TYPE: "core"}
    assert binding_name_and_type, f"vm interface {vm_interface} has not valid binding name."
    return binding_name_and_type


def validate_vnic_info(prometheus: Prometheus, vnic_info_to_compare: dict[str, str], metric_name: str) -> None:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=prometheus.query_sampler,
        query=metric_name,
    )
    sample = None
    try:
        for sample in samples:
            if sample and sample[0].get("metric"):
                vnic_info_metric_result = sample[0].get("metric")
                break
    except TimeoutExpiredError:
        LOGGER.error(f"Metric value of: {metric_name} is: {sample}, should not be empty.")
        raise
    mismatch_vnic_info = {}
    for info, expected_value in vnic_info_to_compare.items():
        actual_value = vnic_info_metric_result.get(info)
        if actual_value != expected_value:
            mismatch_vnic_info[info] = {f"Expected: {expected_value}", f"Actual: {actual_value}"}
    assert not mismatch_vnic_info, f"There is a mismatch between expected and actual results:\n {mismatch_vnic_info}"


def get_metric_labels_non_empty_value(prometheus: Prometheus, metric_name: str) -> dict[str, str]:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=prometheus.query_sampler,
        query=metric_name,
    )
    sample = None
    try:
        for sample in samples:
            if sample and sample[0].get("metric"):
                return sample[0]["metric"]
    except TimeoutExpiredError:
        LOGGER.info(f"Metric value of: {metric_name} is: {sample}, expected value: non empty value.")
        raise
    return {}


@contextmanager
def create_windows11_wsl2_vm(
    dv_name: str,
    namespace: str,
    client: DynamicClient,
    vm_name: str,
    storage_class: str,
) -> Generator:
    """
    Create a Windows 11 WSL2 VM with a DataVolume template

    Args:
        dv_name (str): The name of the DataVolume
        namespace (str): The namespace of the VM
        client (DynamicClient): Client to use to create the VM.
        vm_name (str): The name of the VM
        storage_class (str): The storage class to use for the DataVolume
    """
    artifactory_secret = get_artifactory_secret(namespace=namespace)
    artifactory_config_map = get_artifactory_config_map(namespace=namespace)
    dv = DataVolume(
        name=dv_name,
        namespace=namespace,
        storage_class=storage_class,
        source="http",
        url=get_http_image_url(image_directory=Images.Windows.DIR, image_name=Images.Windows.WIN11_WSL2_IMG),
        size=Images.Windows.DEFAULT_DV_SIZE,
        client=client,
        api_name="storage",
        secret=artifactory_secret,
        cert_configmap=artifactory_config_map.name,
    )
    dv.to_dict()
    with VirtualMachineForTests(
        os_flavor=OS_FLAVOR_WINDOWS,
        name=vm_name,
        namespace=namespace,
        client=client,
        vm_instance_type=VirtualMachineClusterInstancetype(client=client, name="u1.xlarge"),
        vm_preference=VirtualMachineClusterPreference(client=client, name="windows.11"),
        data_volume_template={"metadata": dv.res["metadata"], "spec": dv.res["spec"]},
    ) as vm:
        running_vm(vm=vm)
        yield vm
    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
    )


def get_vm_comparison_info_dict(vm: VirtualMachineForTests) -> dict[str, str]:
    return {
        "name": vm.name,
        "namespace": vm.namespace,
        "status": vm.printable_status.lower(),
    }


def get_vmi_guest_os_kernel_release_info_metric_from_vm(
    vm: VirtualMachineForTests, windows: bool = False
) -> dict[str, str]:
    guest_os_kernel_release = run_ssh_commands(
        host=vm.ssh_exec, commands=shlex.split("ver" if windows else "uname -r")
    )[0].strip()
    if windows:
        guest_os_kernel_release = re.search(r"\[Version\s(\d+\.\d+\.(\d+))", guest_os_kernel_release)
        assert guest_os_kernel_release, "OS kernel release version not found."
        guest_os_kernel_release = guest_os_kernel_release.group(2)
    return {
        "guest_os_kernel_release": guest_os_kernel_release,
        "namespace": vm.namespace,
        NODE_STR: vm.vmi.virt_launcher_pod.node.name,
        "vmi_pod": vm.vmi.virt_launcher_pod.name,
    }


def get_pvc_size_bytes(vm: VirtualMachineForTests) -> str:
    vm_dv_templates = vm.instance.spec.dataVolumeTemplates
    assert vm_dv_templates, "VM has no DataVolume templates"
    return str(
        int(
            bitmath.parse_string_unsafe(
                PersistentVolumeClaim(
                    name=vm_dv_templates[0].metadata.name,
                    namespace=vm.namespace,
                    client=vm.client,
                ).instance.spec.resources.requests.storage
            ).Byte.bytes
        )
    )


def validate_metric_value_greater_than_initial_value(
    prometheus: Prometheus, metric_name: str, initial_value: int, timeout: int = TIMEOUT_4MIN
) -> None:
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_15SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=metric_name,
    )
    try:
        for sample in samples:
            if sample:
                if int(sample) > initial_value:
                    return
    except TimeoutExpiredError:
        LOGGER.error(f"{sample} should be greater than {initial_value}")
        raise


def vnic_info_from_vm_or_vmi(vm_or_vmi: str, vm: VirtualMachineForTests) -> dict[str, str]:
    vm_spec = vm.vmi.instance.spec if vm_or_vmi == "vmi" else vm.instance.spec.template.spec
    vm_interface = vm_spec.domain.devices.interfaces[0]
    binding_name_and_type = binding_name_and_type_from_vm_or_vmi(vm_interface=vm_interface)
    return {
        "vnic_name": vm_spec.networks[0].name,
        BINDING_NAME: binding_name_and_type[BINDING_NAME],
        BINDING_TYPE: binding_name_and_type[BINDING_TYPE],
        "model": vm_interface.model,
    }


def validate_values_from_kube_application_aware_resourcequota_metric(
    prometheus,
    aaq_resource_hard_limit_and_used,
):
    expected_hard_limit, expected_used = aaq_resource_hard_limit_and_used

    def _get_metric_values():
        result = {}
        for item in prometheus.query_sampler(query="kube_application_aware_resourcequota"):
            if "value" in item:
                metric = item["metric"]
                resource = metric["resource"]
                metric_type = metric["type"]
                value = item["value"][1]
                value = int(value) if metric["unit"] == "bytes" else float(value)
                result.setdefault(resource, {})[metric_type] = value
        return result

    for metric_sample in TimeoutSampler(
        sleep=2,
        func=_get_metric_values,
        wait_timeout=TIMEOUT_1MIN,
    ):
        all_match = True

        for resource, expected_hard_value in expected_hard_limit.items():
            expected_used_value = expected_used.get(resource)
            actual_resource_metrics = metric_sample.get(resource, {})
            actual_hard_value = actual_resource_metrics.get("hard")
            actual_used_value = actual_resource_metrics.get("used")
            if actual_hard_value != expected_hard_value or actual_used_value != expected_used_value:
                all_match = False
                break

        if all_match:
            return metric_sample

    raise TimeoutError("Timed out waiting for Prometheus metrics to match expected values.")
