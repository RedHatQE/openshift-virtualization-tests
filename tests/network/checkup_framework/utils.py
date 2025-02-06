import contextlib
import logging
import re

from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.config_map import ConfigMap
from ocp_resources.job import Job
from ocp_resources.role import Role
from ocp_resources.role_binding import RoleBinding
from ocp_resources.service_account import ServiceAccount
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.network.checkup_framework.constants import (
    API_GROUPS_STR,
    RESOURCES_STR,
    VERBS_STR,
)
from utilities.constants import (
    GET_STR,
    TIMEOUT_4MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_11MIN,
    UPDATE_STR,
)
from utilities.exceptions import ResourceValueError
from utilities.infra import get_pods

LOGGER = logging.getLogger(__name__)
MAX_DESIRED_LATENCY_MILLISECONDS = "200"


@contextlib.contextmanager
def create_checkup_job(
    vm_checkup_image,
    service_account,
    configmap_name,
    name,
    env_variables=True,
    security_context=False,
    include_uid=False,
    client=None,
):
    """
    Creates a VM checkup job.
    Args:
        vm_checkup_image (str): The image of the VM checkup. Example of the expected image:
            'registry.redhat.io/container-native-virtualization/vm-network-latency-checkup-rhel9@sha256:<sha_content>'
        service_account (ServiceAccount): The VM latency checkup service account resource.
        configmap_name (str): The name of the configmap resource used for the VM latency checkup.
        name (str): The job name.
        env_variables (bool, default: True): Include the environment variables in the job containers section.
        security_context (bool, default: False): Include the security context in the job containers section.
        include_uid (bool, default: False): Include the uid in the job containers section.
        client (DynamicClient, default=None): Unprivileged or admin client


    Yield:
        Job object.
    """
    containers = [
        {
            "name": name,
            "image": vm_checkup_image,
            "imagePullPolicy": "Always",
            "env": [],
        }
    ]
    if env_variables:
        containers[0]["env"] = [
            {
                "name": "CONFIGMAP_NAMESPACE",
                "value": service_account.namespace,
            },
            {
                "name": "CONFIGMAP_NAME",
                "value": configmap_name,
            },
        ]
    if security_context:
        containers[0]["securityContext"] = {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "runAsNonRoot": True,
            "seccompProfile": {"type": "RuntimeDefault"},
        }
    if include_uid:
        containers[0]["env"].append({
            "name": "POD_UID",
            "valueFrom": {"fieldRef": {"fieldPath": "metadata.uid"}},
        })
    with Job(
        name=name or "latency-job",
        namespace=service_account.namespace,
        service_account=service_account.name,
        restart_policy="Never",
        backoff_limit=0,
        containers=containers,
        background_propagation_policy="Background",
        client=client,
    ) as job:
        yield job


@contextlib.contextmanager
def create_latency_configmap(
    network_attachment_definition_name,
    namespace_name,
    configmap_name,
    timeout="5m",
    max_desired_latency_milliseconds="",
    network_attachment_definition_namespace=None,
    source_node=None,
    target_node=None,
    traffic_pps=None,
    dpdk_gen_target_node=None,
    dpdk_test_target_node=None,
    dpdk_vmgen_container_diskimage=None,
    dpdk_vmtest_container_diskimage=None,
):
    data = compose_configmap_data(
        timeout=timeout,
        network_attachment_definition_namespace=network_attachment_definition_namespace,
        network_attachment_definition_name=network_attachment_definition_name,
        max_desired_latency_milliseconds=max_desired_latency_milliseconds,
        sample_duration_seconds=f"{TIMEOUT_5SEC}",
        source_node=source_node,
        target_node=target_node,
        traffic_pps=traffic_pps,
        dpdk_gen_target_node=dpdk_gen_target_node,
        dpdk_test_target_node=dpdk_test_target_node,
        dpdk_vmgen_container_diskimage=dpdk_vmgen_container_diskimage,
        dpdk_vmtest_container_diskimage=dpdk_vmtest_container_diskimage,
    )
    with ConfigMap(namespace=namespace_name, name=configmap_name, data=data) as configmap:
        yield configmap


def compose_configmap_data(
    network_attachment_definition_name,
    sample_duration_seconds,
    timeout,
    max_desired_latency_milliseconds="",
    network_attachment_definition_namespace=None,
    source_node=None,
    target_node=None,
    traffic_pps=None,
    dpdk_gen_target_node=None,
    dpdk_test_target_node=None,
    dpdk_vmgen_container_diskimage=None,
    dpdk_vmtest_container_diskimage=None,
):
    """
    Compose a dictionary with the ConfigMap data.

    Args:
        network_attachment_definition_name (str): NAD name.
        sample_duration_seconds (str): Latency check duration, in seconds.
        timeout (str): Timeout to wait for the checkup to finish, in minutes.
        max_desired_latency_milliseconds (str, default=""): Maximum desired latency between VMs. If the latency is
             higher than this - the checkup fails. This value should be given in milliseconds.
        network_attachment_definition_namespace (str): Namespace name where the NAD was created.
        source_node (str, default=None): Node hostname. Check latency from this node to the target_node.
        target_node (str, default=None): Node hostname. Check latency from source_node to this node.
        traffic_pps (str, default=None): [DPDK] Traffic Packets per second
        dpdk_gen_target_node (str, default=None): [DPDK] Node name on which generator vmi will be run.
        dpdk_test_target_node (str, default=None): [DPDK] Node name on which test vmi will be run.
        dpdk_vmgen_container_diskimage (str, default=None): [DPDK] Source of trafficGen container image.
        dpdk_vmtest_container_diskimage (str, default=None): [DPDK] Source of vm under test container image.

    Returns:
        dict: Data section of the ConfigMap.
    """
    data_dict = {
        "spec.timeout": timeout,
        "spec.param.sampleDurationSeconds": sample_duration_seconds,
    }
    if max_desired_latency_milliseconds:
        data_dict["spec.param.maxDesiredLatencyMilliseconds"] = max_desired_latency_milliseconds
    if network_attachment_definition_namespace:
        data_dict["spec.param.networkAttachmentDefinitionNamespace"] = network_attachment_definition_namespace
    if network_attachment_definition_name:
        data_dict["spec.param.networkAttachmentDefinitionName"] = network_attachment_definition_name
    if source_node:
        data_dict["spec.param.sourceNode"] = source_node
    if target_node:
        data_dict["spec.param.targetNode"] = target_node
    if traffic_pps:
        data_dict["spec.param.trafficGenPacketsPerSecond"] = traffic_pps
    if dpdk_gen_target_node:
        data_dict["spec.param.trafficGenTargetNodeName"] = dpdk_gen_target_node
    if dpdk_test_target_node:
        data_dict["spec.param.vmUnderTestTargetNodeName"] = dpdk_test_target_node
    if dpdk_vmgen_container_diskimage:
        data_dict["spec.param.trafficGenContainerDiskImage"] = dpdk_vmgen_container_diskimage
    if dpdk_vmtest_container_diskimage:
        data_dict["spec.param.vmUnderTestContainerDiskImage"] = dpdk_vmtest_container_diskimage

    return data_dict


def assert_successful_latency_checkup(configmap):
    configmap_data = configmap.instance.to_dict()["data"]
    assert configmap_data["status.succeeded"] == "true", (
        f"Checkup failed. Reported reason - {configmap_data['status.failureReason']}"
    )
    # Make sure the result parameter are valid:
    assert int(configmap_data["status.result.avgLatencyNanoSec"]) > 0, (
        f"avgLatencyNanoSec is not valid: {configmap_data['status.result.avgLatencyNanoSec']}"
    )
    assert int(configmap_data["status.result.maxLatencyNanoSec"]) > 0, (
        f"maxLatencyNanoSec is not valid: {configmap_data['status.result.maxLatencyNanoSec']}"
    )
    assert int(configmap_data["status.result.maxLatencyNanoSec"]) / 1000000 < int(MAX_DESIRED_LATENCY_MILLISECONDS), (
        f"maxLatencyNanoSec is not valid: {configmap_data['status.result.maxLatencyNanoSec']}"
    )
    assert int(configmap_data["status.result.minLatencyNanoSec"]) > 0, (
        f"minLatencyNanoSec is not valid: {configmap_data['status.result.minLatencyNanoSec']}"
    )


def assert_successful_dpdk_checkup(configmap):
    configmap_data = configmap.instance.to_dict()["data"]
    assert configmap_data["status.succeeded"] == "true", (
        f"Checkup failed. Reported reason - {configmap_data['status.failureReason']}"
    )


def wait_for_job_finish(client, job, checkup_ns, timeout=TIMEOUT_5MIN):
    try:
        job.wait_for_condition(
            condition=job.Condition.COMPLETE,
            status=job.Condition.Status.TRUE,
            timeout=timeout,
        )
    except TimeoutExpiredError:
        pod_last_log_line = get_pod_last_log_line(
            unprivileged_client=client,
            job=job,
            checkup_ns=checkup_ns,
        )
        LOGGER.error(
            f"Couldn't run checkup. Job {job.name} failed. status - {job.instance.status}. \n Error massage "
            f"- last line from the pod log: {pod_last_log_line}"
        )
        raise


def wait_for_job_failure(job):
    if job.name == "latency-nonexistent-node-job":
        timeout = TIMEOUT_11MIN
    else:
        timeout = TIMEOUT_4MIN
    job_status = "not available"
    try:
        job_status = TimeoutSampler(
            wait_timeout=timeout,
            sleep=1,
            func=lambda: filter(
                lambda cond: cond["status"] == job.Condition.Status.TRUE, job.instance.status.conditions
            ),
        )
        for sample in job_status:
            for condition in sample:
                if condition["type"] == job.Status.FAILED:
                    return
                if condition["type"] == job.Status.SUCCEEDED:
                    raise ResourceValueError(f"Job {job.name} has succeeded and should have failed.")
    except TimeoutExpiredError:
        for status in job_status:
            LOGGER.error(f"Job {job.name} current status is {status} and not {job.Status.FAILED} as expected.")
        raise


def get_pod_last_log_line(unprivileged_client, job, checkup_ns):
    for job_pod in get_pods(
        dyn_client=unprivileged_client,
        namespace=checkup_ns,
        label=f"job-name={job.name}",
    ):
        return job_pod.log(tail_lines=1)


def verify_failure_reason_in_log(unprivileged_client, job, checkup_ns, failure_message_regex):
    pod_last_log_line = get_pod_last_log_line(unprivileged_client=unprivileged_client, job=job, checkup_ns=checkup_ns)
    assert re.compile(failure_message_regex).search(pod_last_log_line), (
        f"Error message expected: {failure_message_regex}. Error message received: {pod_last_log_line}."
    )


def assert_source_and_target_nodes(configmap, expected_nodes_identical):
    configmap_instance_data = configmap.instance.data
    source_node = configmap_instance_data["status.result.sourceNode"]
    target_node = configmap_instance_data["status.result.targetNode"]
    if expected_nodes_identical:
        assert source_node == target_node, (
            f"Target and source nodes are not identical: Source node: {source_node}, Target node: {target_node}"
        )
    else:
        assert source_node != target_node, (
            "Target and source nodes should be different, but are identical: "
            f"Source node: {source_node}, Target node: {target_node}"
        )


def assert_failure_reason_in_configmap(configmap, expected_failure_message):
    failure_message = configmap.instance.data["status.failureReason"]
    assert re.findall(expected_failure_message, failure_message), (
        f"Failure massage is {failure_message} and not as expected: {expected_failure_message}"
    )


@contextlib.contextmanager
def generate_checkup_service_account(sa_name_prefix, checkup_namespace_name):
    with ServiceAccount(name=f"{sa_name_prefix}-sa", namespace=checkup_namespace_name) as service_account:
        yield service_account


@contextlib.contextmanager
def checkup_configmap_role(checkup_namespace_name):
    with Role(
        name=f"{checkup_namespace_name}-configmap-role",
        namespace=checkup_namespace_name,
        rules=[
            {
                API_GROUPS_STR: [""],
                RESOURCES_STR: ["configmaps"],
                VERBS_STR: [GET_STR, UPDATE_STR],
            }
        ],
    ) as configmap_role:
        yield configmap_role


@contextlib.contextmanager
def checkup_role_binding(checkup_namespace_name, checkup_service_account, checkup_role):
    with RoleBinding(
        name=checkup_role.name,
        namespace=checkup_namespace_name,
        subjects_kind=checkup_service_account.kind,
        subjects_name=checkup_service_account.name,
        role_ref_kind=checkup_role.kind,
        role_ref_name=checkup_role.name,
    ) as role_binding:
        yield role_binding


@contextlib.contextmanager
def generate_checkup_resources_role(checkup_namespace_name, rules):
    with Role(
        name=f"{checkup_namespace_name}-resources-role",
        namespace=checkup_namespace_name,
        rules=rules,
    ) as checkup_resource_role:
        yield checkup_resource_role


def latency_job_default_name_values(latency_configmap):
    configmap_name = latency_configmap.name
    return {
        "name": configmap_name.replace("configmap", "job"),
        "configmap_name": configmap_name,
    }


def get_job(client, name, namespace_name):
    job = Job(client=client, name=name, namespace=namespace_name)
    if job.exists:
        return job
    raise ResourceNotFoundError(f"No jobs were found in namespace {namespace_name}")
