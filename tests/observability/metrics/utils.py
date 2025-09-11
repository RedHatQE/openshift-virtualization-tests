import logging
import math
import re
import shlex
import urllib
from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine import VirtualMachine
from ocp_utilities.monitoring import Prometheus
from pyhelper_utils.shell import run_command, run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.constants import KUBEVIRT_VIRT_OPERATOR_READY
from tests.observability.metrics.constants import (
    GO_VERSION_STR,
    KUBE_VERSION_STR,
    KUBEVIRT_VMI_FILESYSTEM_BYTES,
    KUBEVIRT_VMI_FILESYSTEM_BYTES_WITH_MOUNT_POINT,
)
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    CAPACITY,
    KUBEVIRT_VIRT_OPERATOR_UP,
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
)
from utilities.infra import get_pod_by_name_prefix
from utilities.monitoring import get_metrics_value
from utilities.storage import wait_for_dv_expected_restart_count
from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)
KUBEVIRT_CR_ALERT_NAME = "KubeVirtCRModified"
CURL_QUERY = "curl -k https://localhost:8443/metrics"
PING = "ping"
JOB_NAME = "kubevirt-prometheus-metrics"
TOPK_VMS = 3
SINGLE_VM = 1
ONE_CPU_CORES = 1
ZERO_CPU_CORES = 0
COUNT_TWO = 2
COUNT_THREE = 3
TOTAL_4_ITERATIONS = 4


def wait_for_metric_vmi_request_cpu_cores_output(prometheus: Prometheus, expected_cpu: int) -> None:
    """
    This function will wait for the expected metrics core cpu to show up in Prometheus query output
    and return if results equal to the expected total requested cpu for all total vm's
    Args:
        prometheus (Prometheus): Prometheus object
        expected_cpu (int):  expected core cpu
    Raise:
        TimeoutExpiredError: if the expected results does not show up in prometheus query output
    """
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=get_prometheus_vmi_request_cpu_sum_query_value,
        prometheus=prometheus,
    )
    sample = None
    try:
        for sample in sampler:
            if round(sample * 10) == expected_cpu:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"timeout exception waiting for prometheus output, expected results: {expected_cpu}\n"
            f"actual results: {sample}"
        )
        raise


def get_prometheus_vmi_request_cpu_sum_query_value(prometheus: Prometheus) -> float:
    """
    This function will perform Prometheus query cluster:vmi_request_cpu_cores:sum and return query cpu output result

    Args:
        prometheus (Prometheus): Prometheus object.

    Returns:
        float: prometheus query value output, return 0.0 if case no results found

    """
    metric_results = prometheus.query(query="cluster:vmi_request_cpu_cores:sum")["data"]["result"]
    return float(metric_results[0]["value"][1]) if metric_results else 0.0


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
    pod = vm.vmi.virt_handler_pod
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
    vm_cpu = vm.instance.spec.template.spec.domain.cpu
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
) -> Resource:
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


def restart_cdi_worker_pod(unprivileged_client: DynamicClient, dv: DataVolume, pod_prefix: str) -> None:
    initial_dv_restartcount = dv.instance.get("status", {}).get("restartCount", 0)
    for iteration in range(TOTAL_4_ITERATIONS - initial_dv_restartcount):
        pod = get_pod_by_name_prefix(
            dyn_client=unprivileged_client,
            pod_prefix=pod_prefix,
            namespace=dv.namespace,
        )
        dv_restartcount = dv.instance.get("status", {}).get("restartCount", 0)
        run_command(
            command=shlex.split(f"oc exec -n {dv.namespace} {pod.name} -- kill 1"),
            check=False,
        )
        wait_for_dv_expected_restart_count(dv=dv, expected_result=dv_restartcount + 1)


def fail_if_not_zero_restartcount(dv: DataVolume) -> None:
    restartcount = dv.instance.get("status", {}).get("restartCount", 0)

    if restartcount != 0:
        pytest.fail(f"dv {dv.name} restartcount is not zero,\n actual restartcount: {restartcount}")


def assert_virtctl_version_equal_metric_output(
    virtctl_server_version: dict[str, str], metric_output: list[dict[str, dict[str, str]]]
) -> None:
    mismatch_result = []
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
    virsh_domifstat_content = vm.privileged_vmi.virt_launcher_pod.execute(
        command=shlex.split(f"virsh domifstat {vm.namespace}_{vm.name} {interface_name}")
    ).splitlines()
    return {line.split()[1]: line.split()[2] for line in virsh_domifstat_content if line}


def compare_network_traffic_bytes_and_metrics(
    prometheus: Prometheus, vm: VirtualMachineForTests, vm_interface_name: str
) -> bool:
    packet_received = network_packets_received(vm=vm, interface_name=vm_interface_name)
    rx_tx_indicator = False
    metric_result = (
        prometheus.query(query=f"kubevirt_vmi_network_traffic_bytes_total{{name='{vm.name}'}}")
        .get("data")
        .get("result")
    )
    for entry in metric_result:
        entry_value = entry.get("value")[1]
        if math.isclose(
            int(entry_value), int(packet_received[f"{entry.get('metric').get('type')}_bytes"]), rel_tol=0.02
        ):
            rx_tx_indicator = True
        else:
            break
    if rx_tx_indicator:
        return True
    return False


def validate_network_traffic_metrics_value(prometheus: Prometheus, vm: VirtualMachine, interface_name: str) -> None:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_4MIN,
        sleep=TIMEOUT_10SEC,
        func=compare_network_traffic_bytes_and_metrics,
        prometheus=prometheus,
        vm=vm,
        vm_interface_name=interface_name,
    )
    try:
        match_counter = 0
        for sample in samples:
            if sample:
                match_counter += 1
                if match_counter > 3:
                    return
            else:
                match_counter = 0

    except TimeoutExpiredError:
        LOGGER.error("Metric value and domistat value not correlate.")
        raise


def get_metric_sum_value(prometheus: Prometheus, metric: str) -> int:
    metrics = prometheus.query(query=metric)
    metrics_result = metrics["data"].get("result", [])
    if metrics_result:
        return sum(int(metric_metrics_result["value"][1]) for metric_metrics_result in metrics_result)
    return 0


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
        r"fs.(\d).(mountpoint|total-bytes|used-bytes)\s+:\s+(.*)\s+",
        vm.privileged_vmi.execute_virsh_command(command="guestinfo --filesystem"),
        re.MULTILINE,
    )
    mount_points_and_values_dict: dict[str, dict[str, str]] = {}
    for fs_id, label, value in lines:
        mount_points_and_values_dict.setdefault(fs_id, {})[label] = value
    return {
        info["mountpoint"]: {USED: info["used-bytes"], CAPACITY: info["total-bytes"]}
        for info in mount_points_and_values_dict.values()
    }


def compare_metric_file_system_values_with_vm_file_system_values(
    prometheus: Prometheus, vm_for_test: VirtualMachineForTests, mount_point: str, capacity_or_used: str
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
                            mountpoint=mount_point,
                        ),
                    )
                )
                if metric_value * 0.95 <= float(sample[mount_point].get(capacity_or_used)) <= metric_value * 1.05:
                    return
    except TimeoutExpiredError:
        LOGGER.info(
            f"Value for mount point: {mount_point} from virsh command: {sample}\n "
            f"Result from metric for the mountpoint: {mount_point}: {metric_value}"
        )
        raise


def expected_metric_labels_and_values(
    prometheus: Prometheus, metric_name: str, expected_labels_and_values: dict[str, str]
) -> None:
    metric_output = prometheus.query_sampler(query=metric_name)[0].get("metric")
    mismatch = {
        label: {f"{label} metric result: {metric_output.get(label)}, expected_label_results: {expected_label_results}"}
        for label, expected_label_results in expected_labels_and_values.items()
        if metric_output.get(label) != expected_label_results
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
