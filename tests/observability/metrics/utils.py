import logging
import math
import re
import shlex
import urllib
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional

import bitmath
import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.pod_metrics import PodMetrics
from ocp_resources.resource import Resource
from ocp_resources.template import Template
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_utilities.monitoring import Prometheus
from podman.errors import ContainerNotFound
from pyhelper_utils.shell import run_command, run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.constants import KUBEVIRT_VIRT_OPERATOR_READY
from tests.observability.metrics.constants import (
    BINDING_NAME,
    BINDING_TYPE,
    GO_VERSION_STR,
    INSTANCE_TYPE_LABELS,
    KUBE_VERSION_STR,
    KUBEVIRT_VMI_FILESYSTEM_BYTES,
    KUBEVIRT_VMI_FILESYSTEM_BYTES_WITH_MOUNT_POINT,
    METRIC_SUM_QUERY,
    RSS_MEMORY_COMMAND,
)
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    CAPACITY,
    KUBEVIRT_VIRT_OPERATOR_UP,
    NODE_STR,
    OS_FLAVOR_WINDOWS,
    RHEL9_PREFERENCE,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_4MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_8MIN,
    TIMEOUT_10MIN,
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
    TIMEOUT_20SEC,
    TIMEOUT_30SEC,
    TIMEOUT_40SEC,
    U1_SMALL,
    USED,
    VIRT_HANDLER,
    Images,
)
from utilities.infra import (
    ExecCommandOnPod,
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_http_image_url,
    get_pod_by_name_prefix,
)
from utilities.monitoring import get_metrics_value
from utilities.network import assert_ping_successful
from utilities.storage import wait_for_dv_expected_restart_count
from utilities.virt import VirtualMachineForTests, VirtualMachineForTestsFromTemplate, running_vm

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


def get_mutation_component_value_from_prometheus(prometheus: Prometheus, component_name: str) -> int:
    query = f'kubevirt_hco_out_of_band_modifications_total{{component_name="{component_name}"}}'
    metric_results = prometheus.query_sampler(query=query)
    return int(metric_results[0]["value"][1]) if metric_results else 0


def get_changed_mutation_component_value(
    prometheus: Prometheus, component_name: str, previous_value: int
) -> Optional[int]:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=10,
        func=get_mutation_component_value_from_prometheus,
        prometheus=prometheus,
        component_name=component_name,
    )
    try:
        for sample in samples:
            if sample != previous_value:
                return sample
    except TimeoutExpiredError:
        LOGGER.error(f"component value did not change for component_name '{component_name}'.")
        raise
    return None


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


def assert_vm_metric(prometheus: Prometheus, query: str, vm_name: str):
    assert get_vm_metrics(prometheus=prometheus, query=query, vm_name=vm_name), (
        f"query: {query} has no result for vm: {vm_name}"
    )


def get_hco_cr_modification_alert_summary_with_count(prometheus: Prometheus, component_name: str) -> str | None:
    """This function will check the 'KubeVirtCRModified'
    an alert summary generated after the 'kubevirt_hco_out_of_band_modifications_total' metrics triggered.

    Args:
        prometheus (:obj:`Prometheus`): Prometheus object.

    Returns:
        String: Summary of the 'KubeVirtCRModified' alert contains count.

        example:
        Alert summary for single change:
        "1 out-of-band CR modifications were detected in the last 10 minutes."
    """

    # Find an alert "KubeVirtCRModified" and return it's summary.
    def _get_summary():
        alerts = prometheus.get_all_alerts_by_alert_name(alert_name=KUBEVIRT_CR_ALERT_NAME)
        for alert in alerts:
            if component_name == alert["labels"]["component_name"]:
                return alert.get("annotations", {}).get("summary")

    # Alert is not updated immediately. Wait for 300 seconds.
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=2,
        func=_get_summary,
    )
    try:
        for alert_summary in samples:
            if alert_summary is not None:
                return alert_summary
    except TimeoutError:
        LOGGER.error(f"Summary is not present for Alert {KUBEVIRT_CR_ALERT_NAME}")
    return None


def wait_for_summary_count_to_be_expected(
    prometheus: Prometheus, component_name: str, expected_summary_value: int
) -> None:
    """This function will wait for the expected summary to match with
    the summary message from component specific alert.

    Args:
        prometheus (:obj:`Prometheus`): Prometheus object.
        component_name (String): Name of the component.
        expected_summary_value (Integer): Expected value of the component after update.

        example:
        Alert summary for 3 times change in component:
        "3 out-of-band CR modifications were detected in the last 10 minutes."
    """

    def extract_value_from_message(message):
        mo = re.search(
            pattern=r"(?P<count>\d+) out-of-band CR modifications were detected in the last (?P<time>\d+) minutes.",
            string=message,
        )
        if mo:
            match_dict = mo.groupdict()
            return int(match_dict["count"])

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=5,
        func=get_hco_cr_modification_alert_summary_with_count,
        prometheus=prometheus,
        component_name=component_name,
    )
    sample = None
    try:
        for sample in samples:
            if sample:
                value = extract_value_from_message(message=sample)
                if value == expected_summary_value:
                    return
    except TimeoutError:
        LOGGER.error(
            f"Summary count did not update for component {component_name}: "
            f"current={sample} expected={expected_summary_value}"
        )
        raise


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


def get_topk_query(metric_names: list[str], time_period: str = "5m") -> str:
    """
    Creates a topk query string based on metric_name

    Args:
        metric_names (list): list of strings

        time_period (str): indicates the time period over which top resources would be considered

    Returns:
        str: query string to be used for the topk query
    """
    query_parts = [f" sum by (name, namespace) (rate({metric}[{time_period}]))" for metric in metric_names]
    return f"topk(3, {(' + ').join(query_parts)})"


def assert_topk_vms(prometheus: Prometheus, query: str, vm_list: list, timeout: int = TIMEOUT_8MIN) -> list | None:
    """
    Performs a topk query against prometheus api, waits until it has expected result entries and returns the
    results

    Args:
        prometheus (Prometheus Object): Prometheus object.
        query (str): Prometheus query string
        vm_list (list): list of vms to show up in topk results
        timeout (int): Timeout value in seconds

    Returns:
        list: List of results

    Raises:
        TimeoutExpiredError: on mismatch between number of vms founds in topk query results vs expected number of vms
    """
    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=5,
        func=prometheus.query_sampler,
        query=urllib.parse.quote_plus(query),
    )
    sample = None
    try:
        for sample in sampler:
            if len(sample) == len(vm_list):
                vms_found = [
                    entry["metric"]["name"] for entry in sample if entry.get("metric", {}).get("name") in vm_list
                ]
                if Counter(vms_found) == Counter(vm_list):
                    return sample
    except TimeoutExpiredError:
        LOGGER.error(
            f'Expected vms: "{vm_list}" for prometheus query:'
            f' "{query}" does not match with actual results: {sample} after {timeout} seconds.'
        )
        raise
    return None


def run_vm_commands(vms: list, commands: list) -> None:
    """
    This helper function, runs commands on vms to generate metrics.
    Args:
        vms (list): List of VirtualMachineForTests
        commands (list): Used to execute commands against nodes (where created vms are scheduled)

    """
    commands = [shlex.split(command) for command in commands]
    LOGGER.info(f"Commands: {commands}")
    for vm in vms:
        if any(command[0].startswith("ping") for command in commands):
            assert_ping_successful(src_vm=vm, dst_ip="localhost", packet_size=10000, count=20)
        else:
            run_ssh_commands(host=vm.ssh_exec, commands=commands)


def run_node_command(vms: list, command: str, utility_pods: list) -> None:
    """
    This is a helper function to run a command against a node associated with a given virtual machine, to prepare
    it for metric generation commands.

    Args:
        vms: (List): List of VirtualMachineForTests objects
        utility_pods (list): Utility pods
        command (str): Command to be run against a given node

    Raise:
        Asserts on command execution failure
    """
    # If multiple vms are placed on the same node, we only want to run command against the node once.
    # So we need to collect the node names first
    node_names = []
    for vm in vms:
        node_name = vm.vmi.node.name
        LOGGER.info(f"For vm {vm.name} is placed on node: {node_name}")
        if node_name not in node_names:
            node_names.append(node_name)
    for node_name in node_names:
        LOGGER.info(f'Running command "{command}" on node {node_name}')
        ExecCommandOnPod(utility_pods=utility_pods, node=node_name).exec(command=command)


def assert_prometheus_metric_values(
    prometheus: Prometheus, query: str, vm: VirtualMachineForTests, timeout: int = TIMEOUT_5MIN
) -> None:
    """
    Compares metric query result with expected values

    Args:
        prometheus (Prometheus Object): Prometheus object.
        query (str): Prometheus query string
        vm (VirtualMachineForTests): Vm that is expected to show up in Prometheus query results
        timeout (int): Timeout value in seconds

    Raise:
        Asserts on premetheus results not matching expected result
    """
    results = get_vm_metrics(prometheus=prometheus, query=query, vm_name=vm.name, timeout=timeout)
    result_entry = []
    if results:
        result_entry = [
            result["metric"] for result in results if result.get("metric") and result["metric"]["name"] == vm.name
        ]

    assert result_entry, f'Prometheus query: "{query}" result: {results} does not include expected vm: {vm.name}'

    expected_result = {
        "job": JOB_NAME,
        "service": JOB_NAME,
        "container": VIRT_HANDLER,
        "kubernetes_vmi_label_kubevirt_io_vm": vm.name,
        "kubernetes_vmi_label_kubevirt_io_nodeName": vm.vmi.node.name,
        "namespace": vm.namespace,
        "pod": vm.vmi.virt_handler_pod,
    }
    metric_value_mismatch = [
        {key: result.get(key, "")}
        for result in result_entry
        for key in expected_result
        if not result.get(key, "") or result[key] != expected_result[key]
    ]
    assert metric_value_mismatch, f"For Prometheus query {query} data validation failed for: {metric_value_mismatch}"


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


def get_vmi_phase_count(prometheus: Prometheus, os_name: str, flavor: str, workload: str, query: str) -> int:
    """
    Get the metric from the defined Prometheus query

    Args:
        prometheus (Prometheus object): Prometheus object to interact with the query
        os_name (str): the OS name as it appears on Prometheus, e.g. windows19
        flavor (str): the flavor as it appears on Prometheus, e.g. tiny
        workload (str): the type of the workload on the VM, e.g. server
        query (str): query str to use according to the query_dict

    Returns:
        the metric value
    """
    query = query.format(os_name=os_name, flavor=flavor, workload=workload)
    LOGGER.debug(f"query for prometheus: query={query}")
    response = prometheus.query_sampler(query=query)
    if not response:
        return 0

    return int(response[0]["value"][1])


def wait_until_kubevirt_vmi_phase_count_is_expected(
    prometheus: Prometheus, vmi_annotations: dict[str, str], expected: str, query: str
) -> None:
    os_name = vmi_annotations[Template.VMAnnotations.OS]
    flavor = vmi_annotations[Template.VMAnnotations.FLAVOR]
    workload = vmi_annotations[Template.VMAnnotations.WORKLOAD]
    LOGGER.info(
        f"Waiting for kubevirt_vmi_phase_count: expected={expected} os={os_name} flavor={flavor} workload={workload}"
    )
    query_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=3,
        func=get_vmi_phase_count,
        prometheus=prometheus,
        os_name=os_name,
        flavor=flavor,
        workload=workload,
        query=query,
    )
    sample = None
    try:
        for sample in query_sampler:
            if sample == expected:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Timeout exception while waiting for a specific value from query: current={sample} expected={expected}"
        )
        raise


def get_prometheus_monitoring_pods(admin_client: DynamicClient) -> list:
    """
    Get all Prometheus pods within the openshift-monitoring namespace

    Args:
        admin_client (DynamicClient): DynamicClient object

    Returns:
        list: list of all prometheus pods within the openshift-monitoring namespace
    """
    prometheus_pods_monitoring_namespace_list = list(
        Pod.get(
            dyn_client=admin_client,
            namespace="openshift-monitoring",
            label_selector=(
                f"{Resource.ApiGroup.APP_KUBERNETES_IO}/name in (prometheus-operator, prometheus, prometheus-adapter)"
            ),
        )
    )
    assert prometheus_pods_monitoring_namespace_list, "no matching pods found on the cluster"
    return prometheus_pods_monitoring_namespace_list


def get_not_running_prometheus_pods(admin_client) -> dict[str, str]:
    """
    Get all Prometheus pods that are not in Running status

    Args:
        admin_client (DynamicClient): DynamicClient object

    Returns:
        dict: dict of prometheus pods' name (key) and status (value) that are not in Running status
    """
    prometheus_pods_monitoring_namespace_list = get_prometheus_monitoring_pods(admin_client=admin_client)
    return {
        pod.name: pod.status for pod in prometheus_pods_monitoring_namespace_list if pod.status != Pod.Status.RUNNING
    }


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


def get_vmi_memory_domain_metric_value_from_prometheus(prometheus: Prometheus, vmi_name: str, query: str) -> int:
    metric_query_output = prometheus.query(query=query)["data"]["result"]
    LOGGER.info(f"Query {query} Output: {metric_query_output}")
    value = [
        int(query_ouput["value"][1])
        for query_ouput in metric_query_output
        if query_ouput["metric"].get("name") == vmi_name
    ]
    assert value, f"Metrics: '{query}' did not return any value, Current Metrics data: {metric_query_output}"
    return value[0]


def get_vmi_dommemstat_from_vm(vmi_dommemstat: str, domain_memory_string: str) -> int:
    # Find string from list in the dommemstat and convert to bytes from KiB.
    vmi_domain_memory_match = re.match(rf".*(?:^|\n|){domain_memory_string} (\d+).*", vmi_dommemstat, re.DOTALL)
    assert vmi_domain_memory_match, (
        f"No match '{domain_memory_string}' found for VM's domain memory in VMI's dommemstat {vmi_dommemstat}"
    )
    matched_vmi_domain_memory_bytes = bitmath.KiB(int(vmi_domain_memory_match.group(1))).to_Byte()
    return matched_vmi_domain_memory_bytes


def get_used_memory_vmi_dommemstat(vm: VirtualMachineForTestsFromTemplate) -> int:
    vmi_dommemstat = vm.privileged_vmi.get_dommemstat()
    available_memory = get_vmi_dommemstat_from_vm(vmi_dommemstat=vmi_dommemstat, domain_memory_string="available")
    usable_memory = get_vmi_dommemstat_from_vm(vmi_dommemstat=vmi_dommemstat, domain_memory_string="usable")

    LOGGER.info(f"Available Memory: {available_memory}. Usable Memory: {usable_memory}")
    return int(available_memory - usable_memory)


def wait_vmi_dommemstat_match_with_metric_value(prometheus: Prometheus, vm: VirtualMachineForTestsFromTemplate) -> None:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=15,
        func=get_used_memory_vmi_dommemstat,
        vm=vm,
    )
    sample = None
    prometheus_metric_value = None
    try:
        for sample in samples:
            if sample:
                prometheus_metric_value = get_metrics_value(
                    prometheus=prometheus, metrics_name=f"kubevirt_vmi_memory_used_bytes{{name='{vm.name}'}}"
                )
                if sample == int(prometheus_metric_value):
                    return
    except TimeoutExpiredError:
        LOGGER.error(
            f"metric value doesn't match with dommemstat, value from prometheus: {prometheus_metric_value}, "
            f"used memory from dommmemstat command: {sample}"
        )
        raise


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


def wait_for_prometheus_query_result_node_value_update(prometheus: Prometheus, query: str, node: str) -> None:
    """
    This function is waiting for Prometheus query node label value to be update.
    Args:
        prometheus (Prometheus): Prometheus object
        query (str): Prometheus query string
        node (str): previous vmi node name
    """
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=prometheus.query_sampler,
        query=query,
    )
    sample = None
    try:
        for sample in sampler:
            if (
                sample
                and sample[0].get("metric")
                and sample[0].get("metric").get("node")
                and sample[0]["metric"]["node"] != node
            ):
                return

    except TimeoutExpiredError:
        LOGGER.error(f"timeout exception waiting  query: {query} Node: {node} to change, results: {sample}")
        raise


def assert_instancetype_labels(prometheus: Prometheus, metric_name: str, expected_labels: dict[str, str]) -> None:
    """
    This function will assert prometheus query output labels against expected labels.

    Args:
        prometheus (Prometheus): Prometheus client object to query metrics
        metric_name (str): The prometheus metric name to query
        expected_labels (dict): Expected instancetype labels to validate against
    """
    validate_metrics_value(prometheus=prometheus, metric_name=metric_name, expected_value="1")

    def check_instancetype_labels():
        data_mismatch = {}
        for label in INSTANCE_TYPE_LABELS:
            prometheus_output = prometheus.query_sampler(query=metric_name)[0].get("metric").get(label)
            if prometheus_output != expected_labels[label]:
                data_mismatch[label] = {"Expected": expected_labels[label], "Actual": prometheus_output}
        return data_mismatch

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_10SEC,
        func=check_instancetype_labels,
    )
    sample = None
    try:
        for sample in samples:
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"timeout exception waiting for instancetype labels to match expected labels: {sample}")
        raise


def wait_for_metric_reset(prometheus: Prometheus, metric_name: str, timeout: int = TIMEOUT_4MIN) -> None:
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_15SEC,
        func=lambda: prometheus.query_sampler(query=metric_name),
    )
    sample = None
    try:
        for sample in samples:
            if not sample:
                return
            else:
                LOGGER.info(f"metric: {metric_name} value is: {sample}, waiting for metric to reset")
    except TimeoutExpiredError:
        LOGGER.info(f"Operator metrics value: {sample}, expected is None")
        raise


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


def wait_for_no_metrics_value(prometheus: Prometheus, metric_name: str) -> None:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=TIMEOUT_40SEC,
        func=prometheus.query,
        query=METRIC_SUM_QUERY.format(
            metric_name=metric_name,
            instance_type_name=U1_SMALL,
            preference=RHEL9_PREFERENCE,
        ),
    )
    counter = 0
    sample = None
    try:
        for sample in samples:
            if not sample.get("data").get("result"):
                counter += 1
                if counter >= 3:
                    return
            else:
                counter = 0
    except TimeoutExpiredError:
        LOGGER.error(f"There is another vms on the cluster: {sample}")
        raise


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
        match_counter = 0
        for sample in samples:
            if sample:
                match_counter += 1
                if match_counter >= 3:
                    return
            else:
                match_counter = 0

    except TimeoutExpiredError:
        LOGGER.error("Metric value and domistat value not correlate.")
        raise


def validate_vmi_network_receive_and_transmit_packets_total(
    metric_dict: dict[str, str],
    vm: VirtualMachineForTests,
    vm_interface_name: str,
    prometheus: Prometheus,
) -> None:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_4MIN,
        sleep=TIMEOUT_10SEC,
        func=network_packets_received,
        vm=vm,
        interface_name=vm_interface_name,
    )
    sample_value = None
    packets_kind = metric_dict["packets_kind"]
    metric_packets_value = None
    values_comparing_history = {}
    try:
        match_counter = 0
        for sample in samples:
            if sample:
                metric_packets_value = get_metrics_value(
                    prometheus=prometheus, metrics_name=f"{metric_dict['metric_name']}{{name='{vm.name}'}}"
                )
                sample_value = sample[packets_kind]
                values_comparing_history[datetime.now()] = (
                    f"Packet kind {packets_kind} value from vm: {sample_value}, "
                    f"metric value for packet kind: {metric_packets_value}"
                )
                if math.isclose(int(sample_value), int(metric_packets_value), rel_tol=0.02):
                    match_counter += 1
                    LOGGER.info(
                        f"Packet kind {packets_kind} and metric value for packet kind match for {match_counter} times"
                    )
                    if match_counter >= 3:
                        LOGGER.info(f"Packet kind {packets_kind} and metric value for packet kind match!")
                        return
                else:
                    match_counter = 0
    except TimeoutExpiredError:
        LOGGER.error(
            f"Expected metric packets value for {packets_kind}: {sample_value}, actual: {metric_packets_value} \n "
            f"History : {values_comparing_history}"
        )
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
    vnic_info_metric_result = prometheus.query_sampler(query=metric_name)[0].get("metric")
    mismatch_vnic_info = {}
    for info, expected_value in vnic_info_to_compare.items():
        actual_value = vnic_info_metric_result.get(info)
        if actual_value != expected_value:
            mismatch_vnic_info[info] = {f"Expected: {expected_value}", f"Actual: {actual_value}"}
    assert not mismatch_vnic_info, f"There is a mismatch between expected and actual results:\n {mismatch_vnic_info}"


def get_interface_name_from_vm(vm: VirtualMachineForTests) -> str:
    interface_name = vm.privileged_vmi.virt_launcher_pod.execute(
        command=shlex.split("bash -c \"virsh domiflist 1 | grep ethernet | awk '{print $1}'\"")
    )
    assert interface_name, f"Interface not found for vm {vm.name}"
    return interface_name


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


def get_pod_memory_stats(admin_client: DynamicClient, hco_namespace: str, pod_prefix: str) -> float:
    return float(
        bitmath.Byte(
            float(
                get_pod_by_name_prefix(
                    dyn_client=admin_client,
                    pod_prefix=pod_prefix,
                    namespace=hco_namespace,
                )
                .execute(command=RSS_MEMORY_COMMAND)
                .strip()
            )
        )
    )


def get_highest_memory_usage_virt_api_pod_tuple(hco_namespace: str) -> tuple[str, int]:
    """
    This function returns pod name and memory value tuple of virt-api pod with the highest memory usage.
        Args:
        hco_namespace: Hco namespacem
    Returns:
        tuple: containing the name of the virt-api pod with the highest memory usage and value of the memory.
    """
    virt_api_with_highest_memory_usage = (
        run_command(
            command=shlex.split(
                f"bash -c 'oc adm top pod -n {hco_namespace} --sort-by memory "
                f"--no-headers -l kubevirt.io=virt-api | head -n 1'"
            ),
        )[1]
        .strip()
        .split()
    )
    return (
        virt_api_with_highest_memory_usage[0],
        int(bitmath.parse_string_unsafe(virt_api_with_highest_memory_usage[2]).Byte),
    )


def get_pod_requested_memory(hco_namespace: str, admin_client: DynamicClient, pod_prefix: str) -> float:
    """
    Get the requested memory for a pod.

    Args:
        hco_namespace: Hco namespace
        admin_client: The Kubernetes admin client
        pod_prefix: Prefix of the pod name to get requested memory from

    Returns:
        float: Requested memory in bytes
    """
    return float(
        bitmath.parse_string_unsafe(
            get_pod_by_name_prefix(
                dyn_client=admin_client,
                pod_prefix=pod_prefix,
                namespace=hco_namespace,
            )
            .instance.spec.containers[0]
            .resources.requests.memory
        ).Byte
    )


def expected_kubevirt_memory_delta_from_requested_bytes(
    hco_namespace: str, admin_client: DynamicClient, rss: bool
) -> int:
    """
    Calculate the expected memory delta between actual and requested memory.

    Args:
        hco_namespace: The namespace where virt-api pods are running
        admin_client: The Kubernetes admin client
        rss: If True, use RSS memory, otherwise use total memory usage

    Returns:
        int: The memory delta in bytes
    """
    pod_name, pod_memory = get_highest_memory_usage_virt_api_pod_tuple(hco_namespace=hco_namespace)
    virt_api_requested_memory = get_pod_requested_memory(
        hco_namespace=hco_namespace,
        admin_client=admin_client,
        pod_prefix=pod_name,
    )
    if rss:
        virt_api_rss_memory = get_pod_memory_stats(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            pod_prefix=pod_name,
        )
        return int(virt_api_rss_memory - virt_api_requested_memory)
    return int(pod_memory - virt_api_requested_memory)


def validate_memory_delta_metrics_value_within_range(
    prometheus: Prometheus,
    metric_name: str,
    rss: bool,
    admin_client: DynamicClient,
    hco_namespace: str,
    timeout: int = TIMEOUT_4MIN,
) -> None:
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_15SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=metric_name,
    )
    sample: int | float = 0
    expected_value = None
    try:
        for sample in samples:
            if sample:
                sample = abs(float(sample))
                expected_value = abs(
                    expected_kubevirt_memory_delta_from_requested_bytes(
                        admin_client=admin_client, hco_namespace=hco_namespace, rss=rss
                    )
                )
                if math.isclose(sample, expected_value, rel_tol=0.05):
                    return
    except TimeoutExpiredError:
        LOGGER.error(f"{sample} should be within 5% of {expected_value}")
        raise


@contextmanager
def create_windows11_wsl2_vm(
    dv_name: str, namespace: str, client: DynamicClient, vm_name: str, storage_class: str
) -> Generator:
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
        vm_instance_type=VirtualMachineClusterInstancetype(name="u1.xlarge"),
        vm_preference=VirtualMachineClusterPreference(name="windows.11"),
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
                ).instance.spec.resources.requests.storage
            ).Byte.bytes
        )
    )


def get_vm_virt_launcher_pod_requested_memory(vm: VirtualMachineForTests) -> int:
    if containers := vm.vmi.virt_launcher_pod.instance.spec.containers:
        return int(bitmath.parse_string_unsafe(containers[0].resources.requests.memory).bytes)
    raise ContainerNotFound(f"No containers found in virt-launcher pod of {vm.vmi.virt_launcher_pod.name}")


def wait_for_virt_launcher_pod_metrics_resource_exists(vm_for_test: VirtualMachineForTests) -> None:
    vl_name = vm_for_test.vmi.virt_launcher_pod.name
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_15SEC,
        func=lambda: PodMetrics(name=vl_name, namespace=vm_for_test.namespace, client=vm_for_test.client).exists,
    )
    try:
        for sample in samples:
            if sample:
                LOGGER.info(f"PodMetric resource for {vl_name} exists.")
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Resource PodMetrics for pod {vl_name} not found")
        raise


def get_vm_memory_working_set_bytes(vm: VirtualMachineForTests) -> int:
    wait_for_virt_launcher_pod_metrics_resource_exists(vm_for_test=vm)
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
        func=run_command,
        command=shlex.split(f"oc adm top pod {vm.vmi.virt_launcher_pod.name} -n {vm.namespace} --no-headers"),
        check=False,
    )
    try:
        for sample in samples:
            if sample and (out := sample[1]):
                if match := re.search(r"\b(\d+)([KMG]i)\b", out):
                    return int(bitmath.parse_string_unsafe(f"{match.group(1)}{match.group(2)}").bytes)
    except TimeoutExpiredError:
        LOGGER.error(f"working_set bytes is not available for VM {vm.name} after {TIMEOUT_2MIN} seconds")
        raise
    return 0


def get_vm_memory_rss_bytes(vm: VirtualMachineForTests) -> int:
    return int(vm.privileged_vmi.virt_launcher_pod.execute(command=RSS_MEMORY_COMMAND))


def validate_metric_vm_container_free_memory_bytes_based_on_working_set_rss_bytes(
    prometheus: Prometheus, metric_name: str, vm: VirtualMachineForTests, working_set=False, timeout: int = TIMEOUT_4MIN
) -> None:
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_15SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=metric_name,
    )
    sample: int | float = 0
    expected_value = None
    try:
        for sample in samples:
            if sample:
                sample = abs(float(sample))
                virt_launcher_pod_requested_memory = get_vm_virt_launcher_pod_requested_memory(vm=vm)
                expected_value = (
                    virt_launcher_pod_requested_memory - get_vm_memory_working_set_bytes(vm=vm)
                    if working_set
                    else virt_launcher_pod_requested_memory - get_vm_memory_rss_bytes(vm=vm)
                )
                if math.isclose(sample, abs(expected_value), rel_tol=0.05):
                    return
    except TimeoutExpiredError:
        LOGGER.error(f"{sample} should be within 5% of {expected_value}")
        raise


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
