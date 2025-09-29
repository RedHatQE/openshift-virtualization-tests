import base64
import io
import json
import logging
import os
import platform
import re
import shlex
import ssl
import stat
import subprocess
import tarfile
import tempfile
import time
import zipfile
from contextlib import contextmanager
from functools import cache
from subprocess import PIPE, CalledProcessError, Popen
from typing import Any

import netaddr
import paramiko
import pytest
import requests
import urllib3
import yaml
from jira import JIRA
from kubernetes.client import ApiException
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError, ResourceNotFoundError
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.config_map import ConfigMap
from ocp_resources.console_cli_download import ConsoleCLIDownload
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.exceptions import ResourceTeardownError
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.infrastructure import Infrastructure
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node
from ocp_resources.package_manifest import PackageManifest
from ocp_resources.pod import Pod
from ocp_resources.project_request import ProjectRequest
from ocp_resources.resource import Resource, ResourceEditor, get_client
from ocp_resources.secret import Secret
from ocp_resources.subscription import Subscription
from ocp_utilities.exceptions import NodeNotReadyError, NodeUnschedulableError
from ocp_utilities.infra import (
    assert_nodes_in_healthy_condition,
    assert_nodes_schedulable,
)
from packaging.version import Version
from pyhelper_utils.shell import run_command
from pytest_testconfig import config as py_config
from requests import HTTPError, Timeout, TooManyRedirects
from timeout_sampler import TimeoutExpiredError, TimeoutSampler, retry

import utilities.virt
from utilities.constants import (
    AMD_64,
    ARTIFACTORY_SECRET_NAME,
    AUDIT_LOGS_PATH,
    CLUSTER,
    CPU_MODEL_LABEL_PREFIX,
    EXCLUDED_CPU_MODELS,
    EXCLUDED_OLD_CPU_MODELS,
    HCO_CATALOG_SOURCE,
    IMAGE_CRON_STR,
    KUBECONFIG,
    KUBELET_READY_CONDITION,
    KUBERNETES_ARCH_LABEL,
    NET_UTIL_CONTAINER_IMAGE,
    OC_ADM_LOGS_COMMAND,
    PROMETHEUS_K8S,
    SANITY_TESTS_FAILURE,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_6MIN,
    TIMEOUT_10MIN,
    TIMEOUT_10SEC,
    TIMEOUT_30SEC,
    VIRTCTL,
    X86_64,
    NamespacesNames,
)
from utilities.data_collector import (
    collect_default_cnv_must_gather_with_vm_gather,
    get_data_collector_dir,
    write_to_file,
)
from utilities.exceptions import (
    ClusterSanityError,
    MissingEnvironmentVariableError,
    OsDictNotFoundError,
    StorageSanityError,
    UrlNotFoundError,
    UtilityPodNotFoundError,
)
from utilities.hco import wait_for_hco_conditions
from utilities.ssp import guest_agent_version_parser
from utilities.storage import get_test_artifact_server_url

JIRA_STATUS_CLOSED = ("on_qa", "verified", "release pending", "closed")
NON_EXIST_URL = "https://noneexist.test"  # Use 'test' domain rfc6761
EXCLUDED_FROM_URL_VALIDATION = ("", NON_EXIST_URL)
INTERNAL_HTTP_SERVER_ADDRESS = "internal-http.cnv-tests-utilities"
HOST_MODEL_CPU_LABEL = f"host-model-cpu.node.{Resource.ApiGroup.KUBEVIRT_IO}"
LOGGER = logging.getLogger(__name__)


def label_project(name, label, admin_client):
    ns = Namespace(client=admin_client, name=name, ensure_exists=True)
    ns.wait_for_status(status=Namespace.Status.ACTIVE, timeout=TIMEOUT_2MIN)
    ResourceEditor({ns: {"metadata": {"labels": label}}}).update()


def create_ns(
    name: str,
    admin_client: DynamicClient,
    unprivileged_client: DynamicClient | None = None,
    labels: dict[str, str] | None = None,
    teardown: bool = True,
    delete_timeout: int = TIMEOUT_6MIN,
):
    """
    For kubemacpool labeling opt-modes, provide kmp_vm_label and admin_client as admin_client
    """
    if not unprivileged_client:
        with Namespace(
            client=admin_client,
            name=name,
            label=labels,
            teardown=teardown,
            delete_timeout=delete_timeout,
        ) as ns:
            ns.wait_for_status(status=Namespace.Status.ACTIVE, timeout=TIMEOUT_2MIN)
            yield ns
    else:
        ProjectRequest(name=name, client=unprivileged_client, teardown=teardown).deploy()
        label_project(name=name, label=labels, admin_client=admin_client)
        ns = Namespace(client=unprivileged_client, name=name, ensure_exists=True)

        yield ns

        ns.client = admin_client
        if teardown and not ns.clean_up():
            raise ResourceTeardownError(resource=ns)


class ClusterHosts:
    class Type:
        VIRTUAL = "virtual"
        PHYSICAL = "physical"


def url_excluded_from_validation(url):
    # Negative URL test cases or internal http server
    return url in EXCLUDED_FROM_URL_VALIDATION or INTERNAL_HTTP_SERVER_ADDRESS in url


def camelcase_to_mixedcase(camelcase_str):
    # Utility to convert CamelCase to mixedCase
    # Example: Service type may be NodePort but in VM attributes.spec.ports it is nodePort
    return camelcase_str[0].lower() + camelcase_str[1:]


def get_pod_by_name_prefix(dyn_client, pod_prefix, namespace, get_all=False):
    """
    Args:
        dyn_client (DynamicClient): OCP Client to use.
        pod_prefix (str): str or regex pattern.
        namespace (str): Namespace name.
        get_all (bool): Return all pods if True else only the first one.

    Returns:
        list or Pod: A list of all matching pods if get_all else only the first pod.

    Raises:
        ResourceNotFoundError: if no pods are found.
    """
    pods = [pod for pod in Pod.get(dyn_client=dyn_client, namespace=namespace) if re.match(pod_prefix, pod.name)]
    if get_all:
        return pods  # Some negative cases check if no pods exists.
    elif pods:
        return pods[0]
    raise ResourceNotFoundError(f"A pod with the {pod_prefix} prefix does not exist")


def generate_namespace_name(file_path):
    return (file_path.strip(".py").replace("/", "-").replace("_", "-"))[-63:].split("-", 1)[-1]


def generate_latest_os_dict(os_list):
    """
    Get latest os dict.

    Args:
        os_list (list): [<os-name>]_os_matrix - a list of dicts.

    Returns:
        dict: {Latest OS name: latest supported OS dict} else raises an exception.

    Raises:
        OsDictNotFoundError: If no os matched.
    """
    for os_dict in os_list:
        for os_version, os_values in os_dict.items():
            if os_values.get("latest_released"):
                return {os_version: os_values}

    raise OsDictNotFoundError(f"No OS is marked as 'latest_released': {os_list}")


def get_latest_os_dict_list(os_list):
    """
    Get latest os dict generated by 'generate_latest_os_dict()'
    This will extract the dict from `generate_latest_os_dict()` without the name key.

    Args:
        os_list (list): [rhel|windows|fedora]_os_matrix - a list of dicts

    Returns:
        list: List of oses dict [{latest supported OS dict}]
    """
    res = []
    for _os in os_list:
        res.append(list(generate_latest_os_dict(os_list=_os).values())[0])
    return res


def base64_encode_str(text):
    return base64.b64encode(text.encode()).decode()


def private_to_public_key(key):
    return paramiko.RSAKey.from_private_key_file(key).get_base64()


def name_prefix(name):
    return name.split(".")[0]


def authorized_key(private_key_path):
    return f"ssh-rsa {private_to_public_key(key=private_key_path)} root@exec1.rdocloud"


def get_jira_status(jira):
    env_var = os.environ
    if not (env_var.get("PYTEST_JIRA_TOKEN") and env_var.get("PYTEST_JIRA_URL")):
        raise MissingEnvironmentVariableError("Please set PYTEST_JIRA_TOKEN and PYTEST_JIRA_URL environment variables")

    jira_connection = JIRA(
        token_auth=env_var["PYTEST_JIRA_TOKEN"],
        options={"server": env_var["PYTEST_JIRA_URL"]},
    )
    return jira_connection.issue(id=jira).fields.status.name.lower()


def get_pods(dyn_client: DynamicClient, namespace: Namespace, label: str = "") -> list[Pod]:
    return list(
        Pod.get(
            dyn_client=dyn_client,
            namespace=namespace.name,
            label_selector=label,
        )
    )


def wait_for_pods_deletion(pods):
    for pod in pods:
        pod.wait_deleted()


def get_pod_container_error_status(pod: Pod) -> str | None:
    try:
        pod_instance_status = pod.instance.status
        # Check the containerStatuses and if any container is in waiting state, return that information:
        for container_status in pod_instance_status.get("containerStatuses", []):
            if waiting_container := container_status.get("state", {}).get("waiting"):
                return waiting_container["reason"] if waiting_container.get("reason") else waiting_container
        return None
    except NotFoundError:
        LOGGER.error(f"Pod {pod.name} was not found")
        raise


def get_not_running_pods(pods: list[Pod], filter_pods_by_name: str = "") -> list[dict[str, str]]:
    pods_not_running = []
    for pod in pods:
        if filter_pods_by_name and filter_pods_by_name in pod.name:
            LOGGER.warning(f"Ignoring pod: {pod.name} for pod state validations.")
            continue
        try:
            pod_instance = pod.instance
            # Waits for all pods in a given namespace to be in final healthy state(running/completed).
            # We also need to keep track of pods marked for deletion as not running. This would ensure any
            # pod that was spinned up in place of pod marked for deletion, reaches healthy state before end
            # of this check
            if pod_instance.metadata.get("deletionTimestamp") or pod_instance.status.phase not in (
                pod.Status.RUNNING,
                pod.Status.SUCCEEDED,
            ):
                pods_not_running.append({pod.name: pod.status})
            elif container_status_error := get_pod_container_error_status(pod=pod):
                pods_not_running.append({pod.name: container_status_error})
        except (ResourceNotFoundError, NotFoundError):
            LOGGER.warning(f"Ignoring pod {pod.name} that disappeared during cluster sanity check")
            pods_not_running.append({pod.name: "Deleted"})
    return pods_not_running


def wait_for_pods_running(
    admin_client: DynamicClient,
    namespace: Namespace,
    number_of_consecutive_checks: int = 1,
    filter_pods_by_name: str = "",
) -> None:
    """
    Waits for all pods in a given namespace to reach Running/Completed state. To avoid catching all pods in running
    state too soon, use number_of_consecutive_checks with appropriate values.
    Args:
         admin_client(DynamicClient): Dynamic client
         namespace(Namespace): A namespace object
         number_of_consecutive_checks(int): Number of times to check for all pods in running state
         filter_pods_by_name(str): string to filter pod names by
    Raises:
        TimeoutExpiredError: Raises TimeoutExpiredError if any of the pods in the given namespace are not in Running
         state
    """
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
        func=get_pods,
        dyn_client=admin_client,
        namespace=namespace,
        exceptions_dict={NotFoundError: []},
    )

    not_running_pods = []
    try:
        current_check = 0
        for sample in samples:
            if sample:
                if not_running_pods := get_not_running_pods(pods=sample, filter_pods_by_name=filter_pods_by_name):
                    LOGGER.warning(f"Not running pods: {not_running_pods}")
                    current_check = 0
                else:
                    current_check += 1
                    if current_check >= number_of_consecutive_checks:
                        return
    except TimeoutExpiredError:
        if not_running_pods:
            LOGGER.error(
                f"timeout waiting for all pods in namespace {namespace.name} to reach "
                f"running state, following pods are in not running state: {not_running_pods}"
            )
            raise


def get_daemonset_by_name(admin_client, daemonset_name, namespace_name):
    """
    Gets a daemonset object by name

    Args:
        admin_client (DynamicClient): a DynamicClient object
        daemonset_name (str): Name of the daemonset
        namespace_name (str): Name of the associated namespace

    Returns:
        Daemonset: Daemonset object
    """
    daemon_set = DaemonSet(
        client=admin_client,
        namespace=namespace_name,
        name=daemonset_name,
    )
    if daemon_set.exists:
        return daemon_set
    raise ResourceNotFoundError(f"Daemonset: {daemonset_name} not found in namespace: {namespace_name}")


def wait_for_consistent_resource_conditions(
    dynamic_client,
    expected_conditions,
    resource_kind,
    stop_conditions=None,
    condition_key1="type",
    condition_key2="status",
    namespace=None,
    total_timeout=TIMEOUT_10MIN,
    polling_interval=5,
    consecutive_checks_count=10,
    exceptions_dict=None,
    resource_name=None,
):
    """This function awaits certain conditions of a given resource_kind (HCO, CSV, etc.).

    Using TimeoutSampler loop and poll the CR (of the resource_kind type) and attempt to match the expected conditions
    against the actual conditions found in the CR.
    Since the conditions statuses might change, we use consecutive checks in order to have consistent results (stable),
    thereby ascertaining that the expected conditions are met over time.

    Args:
        dynamic_client (DynamicClient): admin client
        namespace (str, default: None): resource namespace. Not needed for cluster-scoped resources.
        expected_conditions (dict): a dict comprises expected conditions to meet, for example:
            {<condition key's value>: <condition key's value>,
            Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,}
        stop_conditions (dict, optional): A dict comprising conditions that should not be met.
            The keys represent the value of the `type` field in a condition, and the values represent the value of the
            `reason` field, for example:
            {<condition type key's value>: <condition reason key's value>}
            If any of the stop condition are met, the function will not wait for the expected_conditions.
        resource_kind (Resource): (e.g. HyperConverged, ClusterServiceVersion)
        condition_key1 (str): the key of the first condition in the actual resource_kind (e.g. type, reason, status)
        condition_key2 (str): the key of the second condition in the actual resource_kind (e.g. type, reason, status)
        total_timeout (int): total timeout to wait for (seconds)
        polling_interval (int): the time to sleep after each iteration (seconds)
        consecutive_checks_count (int): the number of repetitions for the status check to make sure the transition is
        done.
            The default value for this argument is not absolute, and there are situations in which it should be higher
            in order to ascertain the consistency of the Ready status.
            Possible situations:
            1. the resource is in a Ready status, because the process (that should cause
            the change in its state) has not started yet.
            2. some components are in Ready status, but others have not started the process yet.
        exceptions_dict: TimeoutSampler exceptions_dict

    Raises:
        TimeoutExpiredError: raised when expected conditions are not met within the timeframe
    """
    samples = TimeoutSampler(
        wait_timeout=total_timeout,
        sleep=polling_interval,
        func=lambda: list(
            resource_kind.get(
                dyn_client=dynamic_client,
                namespace=namespace,
                name=resource_name,
            )
        ),
        exceptions_dict=exceptions_dict,
    )
    current_check = 0
    actual_conditions = {}
    LOGGER.info(
        f"Waiting for resource to stabilize: resource_kind={resource_kind.__name__} conditions={expected_conditions} "
        f"sleep={total_timeout} consecutive_checks_count={consecutive_checks_count}"
    )
    try:
        for sample in samples:
            status_conditions = sample[0].instance.get("status", {}).get("conditions")
            if status_conditions:
                actual_conditions = {
                    condition[condition_key1]: condition[condition_key2]
                    for condition in status_conditions
                    if condition[condition_key1] in expected_conditions
                }
                if actual_conditions == expected_conditions:
                    current_check += 1
                    if current_check >= consecutive_checks_count:
                        return
                    continue
                else:
                    current_check = 0
                    if stop_conditions:
                        actual_conditions = {condition["type"]: condition["reason"] for condition in status_conditions}
                        matched_stop_conditions = {
                            type: reason
                            for type, reason in stop_conditions.items()
                            if type in actual_conditions and actual_conditions[type] == reason
                        }
                        if matched_stop_conditions:
                            LOGGER.error(
                                f"Execution halted due to matched stop conditions: {matched_stop_conditions}. "
                                f"Current status conditions: {status_conditions}."
                            )
                            raise TimeoutExpiredError(
                                f"Stop condition met for {resource_kind.__name__}/{resource_name}."
                            )

    except TimeoutExpiredError:
        LOGGER.error(
            f"Timeout expired meeting conditions for resource: resource={resource_kind.kind} "
            f"expected_conditions={expected_conditions} status_conditions={actual_conditions}"
        )
        raise


def raise_multiple_exceptions(exceptions):
    """Raising multiple exceptions

    To be used when multiple exceptions need to be raised, for example when using TimeoutSampler,
    and additional information should be added (so it is viewable in junit report).
    Example:
        except TimeoutExpiredError as exp:
            raise_multiple_exceptions(
                exceptions=[
                    ValueError(f"Error message: {output}"),
                    exp,
                ]
            )

    Args:
        exceptions (list): List of exceptions to be raised. The 1st exception will appear in pytest error message;
                           all exceptions will appear in the stacktrace.

    """
    # After all exceptions were raised
    if not exceptions:
        return
    try:
        raise exceptions.pop()
    finally:
        raise_multiple_exceptions(exceptions=exceptions)


def get_node_pod(utility_pods, node):
    """
    This function will return a pod based on the node specified as an argument.

    Args:
        utility_pods (list): List of utility pods.
        node (Node or str): Node to get the pod for it.
    """
    _node_name = node.name if hasattr(node, "name") else node
    for pod in utility_pods:
        if pod.node.name == _node_name:
            return pod


class ExecCommandOnPod:
    def __init__(self, utility_pods, node):
        """
        Run command on pod with chroot /host

        Args:
            utility_pods (list): List of utility pods resources.
            node (Node): Node resource.

        Returns:
            str: Command output
        """
        self.pod = get_node_pod(utility_pods=utility_pods, node=node)
        if not self.pod:
            raise UtilityPodNotFoundError(node=node.name)

    def exec(self, command, chroot_host=True, ignore_rc=False, timeout=TIMEOUT_1MIN):
        chroot_command = "chroot /host" if chroot_host else ""
        _command = shlex.split(f"{chroot_command} bash -c {shlex.quote(command)}")
        return self.pod.execute(command=_command, ignore_rc=ignore_rc, timeout=timeout).strip()

    def get_interface_ip(self, interface):
        out = self.exec(command=f"ip addr show {interface}")
        match_ip = re.search(r"[0-9]+(?:\.[0-9]+){3}", out)
        if match_ip:
            interface_ip = match_ip.group()
            if netaddr.valid_ipv4(interface_ip):
                return interface_ip

    @property
    def reboot(self):
        try:
            self.exec(command="sudo echo b > /proc/sysrq-trigger")
        except ApiException:
            return True
        return False

    @property
    def is_connective(self):
        return self.exec(command="ls")

    def interface_status(self, interface):
        return self.exec(command=f"cat /sys/class/net/{interface}/operstate")

    @property
    def release_info(self):
        out = self.exec(command="cat /etc/os-release")
        release_info = {}
        for line in out.strip().splitlines():
            values = line.split("=", 1)
            if len(values) != 2:
                continue
            release_info[values[0].strip()] = values[1].strip(" \"'")
        return release_info


def storage_sanity_check(cluster_storage_classes_names):
    config_sc = list([[*csc][0] for csc in py_config["storage_class_matrix"]])
    exists_sc = [scn for scn in config_sc if scn in cluster_storage_classes_names]
    if sorted(config_sc) != sorted(exists_sc):
        LOGGER.error(f"Expected {config_sc}, On cluster {exists_sc}")
        return False
    return True


def cluster_sanity(
    request,
    admin_client,
    cluster_storage_classes_names,
    nodes,
    hco_namespace,
    hco_status_conditions,
    expected_hco_status,
    junitxml_property=None,
):
    if "cluster_health_check" in request.config.getoption("-m"):
        LOGGER.warning("Skipping cluster sanity test, got -m cluster_health_check")
        return

    skip_cluster_sanity_check = "--cluster-sanity-skip-check"
    skip_storage_classes_check = "--cluster-sanity-skip-storage-check"
    skip_nodes_check = "--cluster-sanity-skip-nodes-check"
    exceptions_filename = "cluster_sanity_failure.txt"
    try:
        if request.session.config.getoption(skip_cluster_sanity_check):
            LOGGER.warning(f"Skipping cluster sanity check, got {skip_cluster_sanity_check}")
            return
        LOGGER.info(
            f"Running cluster sanity. (To skip cluster sanity check pass {skip_cluster_sanity_check} to pytest)"
        )
        # Check storage class only if --cluster-sanity-skip-storage-check not passed to pytest.
        if request.session.config.getoption(skip_storage_classes_check):
            LOGGER.warning(f"Skipping storage classes check, got {skip_storage_classes_check}")
        else:
            LOGGER.info(
                f"Check storage classes sanity. (To skip storage class sanity check pass {skip_storage_classes_check} "
                f"to pytest)"
            )
            if not storage_sanity_check(cluster_storage_classes_names=cluster_storage_classes_names):
                raise StorageSanityError(
                    err_str=f"Cluster is missing storage class.\n"
                    f"either run with '--storage-class-matrix' or with '{skip_storage_classes_check}'"
                )

        # Check nodes only if --cluster-sanity-skip-nodes-check not passed to pytest.
        if request.session.config.getoption(skip_nodes_check):
            LOGGER.warning(f"Skipping nodes check, got {skip_nodes_check}")

        else:
            # validate that all the nodes are ready and schedulable and CNV pods are running
            LOGGER.info(f"Check nodes sanity. (To skip nodes sanity check pass {skip_nodes_check} to pytest)")
            assert_nodes_in_healthy_condition(nodes=nodes, healthy_node_condition_type=KUBELET_READY_CONDITION)
            assert_nodes_schedulable(nodes=nodes)

            try:
                wait_for_pods_running(
                    admin_client=admin_client,
                    namespace=hco_namespace,
                    filter_pods_by_name=IMAGE_CRON_STR,
                )
            except TimeoutExpiredError as timeout_error:
                LOGGER.error(timeout_error)
                raise ClusterSanityError(
                    err_str=f"Timed out waiting for all pods in namespace {hco_namespace.name} to get to running state."
                )
        # Wait for hco to be healthy
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
    except (ClusterSanityError, NodeUnschedulableError, NodeNotReadyError, StorageSanityError) as ex:
        exit_pytest_execution(
            filename=exceptions_filename,
            message=str(ex),
            junitxml_property=junitxml_property,
        )


class ResourceMismatch(Exception):
    pass


def exit_pytest_execution(message, return_code=SANITY_TESTS_FAILURE, filename=None, junitxml_property=None):
    """Exit pytest execution

    Exit pytest execution; invokes pytest_sessionfinish.
    Optionally, log an error message to tests-collected-info/utilities/pytest_exit_errors/<filename>

    Args:
        message (str):  Message to display upon exit and to log in errors file
        return_code (int. Default: 99): Exit return code
        filename (str, optional. Default: None): filename where the given message will be saved
        junitxml_property (pytest plugin): record_testsuite_property
    """
    target_location = os.path.join(get_data_collector_dir(), "pytest_exit_errors")
    # collect must-gather for past 5 minutes:
    if return_code == SANITY_TESTS_FAILURE:
        try:
            collect_default_cnv_must_gather_with_vm_gather(
                since_time=TIMEOUT_5MIN,
                target_dir=target_location,
            )
        except Exception as current_exception:
            LOGGER.warning(f"Failed to collect logs cnv must-gather after cluster_sanity failure: {current_exception}")

    if filename:
        write_to_file(
            file_name=filename,
            content=message,
            base_directory=target_location,
        )
    if junitxml_property:
        junitxml_property(name="exit_code", value=return_code)
    pytest.exit(reason=message, returncode=return_code)


def get_kubevirt_package_manifest(admin_client):
    return get_raw_package_manifest(
        admin_client=admin_client,
        name=py_config["hco_cr_name"],
        catalog_source=HCO_CATALOG_SOURCE,
    )


def get_raw_package_manifest(admin_client, name, catalog_source):
    """
    Gets PackageManifest ResourceField associated with catalog source.
    Multiple PackageManifest Resources exist with the same name but different labels.
    Requires raw=True

    Args:
        admin_client (DynamicClient): dynamic client object
        name (str): Name of PackageManifest
        catalog_source (str): Catalog source

    Returns:
        ResourceField or None: PackageManifest ResourceField or None if no matching resource found
    """
    for resource_field in PackageManifest.get(
        dyn_client=admin_client,
        namespace=py_config["marketplace_namespace"],
        field_selector=f"metadata.name={name}",
        label_selector=f"catalog={catalog_source}",
        raw=True,  # multiple packagemanifest exists with the same name but different labels
    ):
        LOGGER.info(
            f"Found expected packagemanefest: {resource_field.metadata.name}: "
            f"in catalog: {resource_field.metadata.labels.catalog}"
        )
        return resource_field
    LOGGER.warning(f"Not able to find any packagemanifest {name} in {catalog_source} source.")


def get_subscription(admin_client, namespace, subscription_name):
    """
    Gets subscription by name

    Args:
        admin_client (DynamicClient): Dynamic client object
        namespace (str): Name of the namespace
        subscription_name (str): Name of the subscription

    Returns:
        Resource: subscription resource

    Raises:
        NotFoundError: when a given subscription is not found in a given namespace
    """
    subscription = Subscription(
        client=admin_client,
        name=subscription_name,
        namespace=namespace,
    )
    if subscription.exists:
        return subscription
    raise ResourceNotFoundError(f"Subscription {subscription_name} not found in namespace: {namespace}")


def get_csv_by_name(csv_name, admin_client, namespace):
    """
    Gets csv from a given namespace by name

    Args:
        csv_name (str): Name of the csv
        admin_client (DynamicClient): dynamic client object
        namespace (str): namespace name

    Returns:
        Resource: csv resource

    Raises:
        NotFoundError: when a given csv is not found in a given namespace
    """
    csv = ClusterServiceVersion(client=admin_client, namespace=namespace, name=csv_name)
    if csv.exists:
        return csv
    raise ResourceNotFoundError(f"Csv {csv_name} not found in namespace: {namespace}")


def get_clusterversion(dyn_client):
    for cvo in ClusterVersion.get(dyn_client=dyn_client):
        return cvo


def get_deployments(admin_client, namespace):
    return list(Deployment.get(dyn_client=admin_client, namespace=namespace))


def get_related_images_name_and_version(csv):
    related_images = {}
    for item in csv.instance.spec.relatedImages:
        # Example: 'registry.redhat.io/container-native-virtualization/node-maintenance-operator:v2.6.3-1'
        image_name = re.search(r".*/(?P<name>.*?):(.*)", item["name"]).group(1)
        if image_name:
            related_images[image_name] = item["image"]
    LOGGER.info(f"From {csv.name} the related image information gathered: {related_images}")
    return related_images


def run_virtctl_command(command, virtctl_binary=VIRTCTL, namespace=None, check=False, verify_stderr=True):
    """
    Run virtctl command

    Args:
        virtctl_binary (str): virtctl binary including full path to binary
        command (list): Command to run
        namespace (str, default:None): Namespace to send to virtctl command
        check (bool, default:False): If check is True and the exit code was non-zero, it raises a
            CalledProcessError

    Returns:
        tuple: True, out if command succeeded, False, err otherwise.
    """
    virtctl_cmd = [virtctl_binary]
    kubeconfig = os.getenv(KUBECONFIG)
    if namespace:
        virtctl_cmd.extend(["-n", namespace])

    if kubeconfig:
        virtctl_cmd.extend(["--kubeconfig", kubeconfig])

    virtctl_cmd.extend(command)
    return run_command(command=virtctl_cmd, check=check, verify_stderr=verify_stderr)


def get_hco_mismatch_statuses(hco_status_conditions, expected_hco_status):
    current_status = {condition["type"]: condition["status"] for condition in hco_status_conditions}
    mismatch_statuses = []

    for condition_type, condition_status in expected_hco_status.items():
        if current_status[condition_type] != condition_status:
            mismatch_statuses.append(
                f"Current condition type {condition_type} does not match expected status {condition_status}"
            )

    return mismatch_statuses


def is_jira_open(jira_id):
    """
    Check if jira status is open.
    Args:
        jira_id (string): Jira card ID in format: "CNV-<jira_id>"
    Returns:
        True: if jira is open
        False: if jira is closed
    """
    jira_status = get_jira_status(jira=jira_id)
    if jira_status not in JIRA_STATUS_CLOSED:
        LOGGER.info(f"Jira {jira_id}: status is {jira_status}")
        return True
    return False


def get_hyperconverged_resource(client, hco_ns_name):
    hco_name = py_config["hco_cr_name"]
    hco = HyperConverged(
        client=client,
        namespace=hco_ns_name,
        name=hco_name,
    )
    if hco.exists:
        return hco
    raise ResourceNotFoundError(f"Hyperconverged: {hco_name} not found in {hco_ns_name}")


def get_utility_pods_from_nodes(nodes, admin_client, label_selector):
    pods = list(Pod.get(dyn_client=admin_client, label_selector=label_selector))
    nodes_without_utility_pods = [node.name for node in nodes if node.name not in [pod.node.name for pod in pods]]
    assert not nodes_without_utility_pods, (
        f"Missing pods with label {label_selector} for: {' '.join(nodes_without_utility_pods)}"
    )
    return [pod for pod in pods if pod.node.name in [node.name for node in nodes]]


def label_nodes(nodes, labels):
    updates = [ResourceEditor({node: {"metadata": {"labels": labels}}}) for node in nodes]

    for update in updates:
        update.update(backup_resources=True)
    yield nodes
    for update in updates:
        update.restore()


def get_daemonsets(admin_client, namespace):
    return list(DaemonSet.get(dyn_client=admin_client, namespace=namespace))


@contextmanager
def scale_deployment_replicas(deployment_name, namespace, replica_count):
    """
    It scales deployments replicas. At the end of the test restores them back
    """
    deployment = Deployment(name=deployment_name, namespace=namespace)
    initial_replicas = deployment.instance.spec.replicas
    deployment.scale_replicas(replica_count=replica_count)
    deployment.wait_for_replicas(deployed=replica_count > 0)
    yield
    deployment.scale_replicas(replica_count=initial_replicas)
    deployment.wait_for_replicas(deployed=initial_replicas > 0)


def get_console_spec_links(admin_client, name):
    console_cli_download_resource_content = ConsoleCLIDownload(name=name, client=admin_client)
    if console_cli_download_resource_content.exists:
        return console_cli_download_resource_content.instance.spec.links

    raise ResourceNotFoundError(f"{name} ConsoleCLIDownload not found")


def get_all_console_links(console_cli_downloads_spec_links):
    all_urls = [entry["href"] for entry in console_cli_downloads_spec_links]
    assert all_urls, (
        "No URL entries found in the resource: "
        f"console_cli_download_resource_content={console_cli_downloads_spec_links}"
    )
    return all_urls


def download_and_extract_file_from_cluster(tmpdir, url):
    """
    Download and extract archive file from the cluster

    Args:
        tmpdir (py.path.local): temporary folder to download the files.
        url (str): URL to download from.

    Returns:
        list: list of extracted filenames
    """
    zip_file_extension = ".zip"
    LOGGER.info(f"Downloading archive using: url={url}")
    urllib3.disable_warnings()  # TODO: remove this when we fix the SSL warning
    local_file_name = os.path.join(tmpdir, url.split("/")[-1])
    with requests.get(url, verify=False, stream=True) as created_request:
        created_request.raise_for_status()
        with open(local_file_name, "wb") as file_downloaded:
            for chunk in created_request.iter_content(chunk_size=8192):
                file_downloaded.write(chunk)
    LOGGER.info("Extract the downloaded archive.")
    if url.endswith(zip_file_extension):
        archive_file_object = zipfile.ZipFile(file=local_file_name)
    else:
        archive_file_object = tarfile.open(name=local_file_name, mode="r")
    archive_file_object.extractall(path=tmpdir)
    extracted_filenames = (
        archive_file_object.namelist() if url.endswith(zip_file_extension) else archive_file_object.getnames()
    )
    LOGGER.info(f"Downloaded file: {extracted_filenames}")
    if os.path.isfile(local_file_name):
        os.remove(local_file_name)
    return [os.path.join(tmpdir.strpath, namelist) for namelist in extracted_filenames]


def get_and_extract_file_from_cluster(urls, system_os, dest_dir, machine_type=None):
    if not machine_type:
        machine_type = get_machine_platform()
    for url in urls:
        if system_os in url and machine_type in url:
            extracted_files = download_and_extract_file_from_cluster(tmpdir=dest_dir, url=url)
            assert len(extracted_files) == 1, (
                f"Only a single file expected in archive: extracted_files={extracted_files}"
            )
            return extracted_files[0]

    raise UrlNotFoundError(f"Url not found for system_os={system_os}")


def download_file_from_cluster(get_console_spec_links_name, dest_dir):
    console_cli_links = get_console_spec_links(
        admin_client=get_client(),
        name=get_console_spec_links_name,
    )
    download_urls = get_all_console_links(console_cli_downloads_spec_links=console_cli_links)
    os_system = platform.system().lower()

    if os_system == "darwin" and platform.mac_ver()[0]:
        os_system = "mac"

    binary_file = get_and_extract_file_from_cluster(
        system_os=os_system,
        urls=download_urls,
        dest_dir=dest_dir,
        machine_type=get_machine_platform(),
    )
    os.chmod(binary_file, stat.S_IRUSR | stat.S_IXUSR)
    return binary_file


def get_machine_platform():
    os_machine_type = platform.machine()
    return AMD_64 if os_machine_type == X86_64 else os_machine_type


def get_nodes_with_label(nodes, label):
    return [node for node in nodes if label in node.labels.keys()]


def get_daemonset_yaml_file_with_image_hash(generated_pulled_secret=None, service_account=None):
    ds_yaml_file = os.path.abspath("utilities/manifests/utility-daemonset.yaml")

    image_info = utilities.virt.get_oc_image_info(
        image=NET_UTIL_CONTAINER_IMAGE,
        pull_secret=generated_pulled_secret,
    )
    with open(ds_yaml_file) as fd:
        ds_yaml = yaml.safe_load(fd.read())

    template_spec = ds_yaml["spec"]["template"]["spec"]
    container = template_spec["containers"][0]
    container["image"] = f"{container['image']}@{image_info.get('listDigest')}"
    template_spec["containers"][0] = container
    if service_account:
        template_spec["serviceAccount"] = service_account.name
        template_spec["serviceAccountName"] = service_account.name
    return io.StringIO(yaml.dump(ds_yaml))


def unique_name(name, service_type=None):
    # Sets unique name
    service_type = f"{service_type}-" if service_type else ""
    return f"{name}-{service_type}{time.time()}".replace(".", "-")


def get_http_image_url(image_directory, image_name):
    return f"{get_test_artifact_server_url()}{image_directory}/{image_name}"


def get_openshift_pull_secret(client: DynamicClient = None) -> Secret:
    pull_secret_name = "pull-secret"
    secret = Secret(
        client=client or get_client(),
        name=pull_secret_name,
        namespace=NamespacesNames.OPENSHIFT_CONFIG,
    )
    assert secret.exists, f"Pull-secret {pull_secret_name} not found in namespace {NamespacesNames.OPENSHIFT_CONFIG}"
    return secret


def generate_openshift_pull_secret_file(client: DynamicClient = None) -> str:
    pull_secret = get_openshift_pull_secret(client=client)
    pull_secret_path = tempfile.mkdtemp(suffix="-cnv-tests-pull-secret")
    json_file = os.path.join(pull_secret_path, "pull-secrets.json")
    secret = base64.b64decode(pull_secret.instance.data[".dockerconfigjson"]).decode(encoding="utf-8")
    with open(file=json_file, mode="w") as outfile:
        outfile.write(secret)
    return json_file


@retry(
    wait_timeout=TIMEOUT_30SEC,
    sleep=TIMEOUT_10SEC,
    exceptions_dict={RuntimeError: []},
)
def get_node_audit_log_entries(log, node, log_entry):
    lines = subprocess.getoutput(
        f"{OC_ADM_LOGS_COMMAND} {node} {AUDIT_LOGS_PATH}/{log} | grep {shlex.quote(log_entry)}"
    ).splitlines()
    has_errors = any(line.startswith("error:") for line in lines)
    if has_errors:
        if any(line.startswith("404 page not found") for line in lines):
            LOGGER.warning(f"Skipping {log} check as it was rotated:\n{lines}")
            return True, []
        LOGGER.warning(f"oc command failed for node {node}, log {log}:\n{lines}")
        raise RuntimeError
    return True, lines


def get_node_audit_log_line_dict(logs, node, log_entry):
    for log in logs:
        _, deprecated_api_lines = get_node_audit_log_entries(log=log, node=node, log_entry=log_entry)
        if deprecated_api_lines:
            for line in deprecated_api_lines:
                try:
                    yield json.loads(line)
                except json.decoder.JSONDecodeError:
                    LOGGER.error(f"Unable to parse line: {line!r}")
                    raise


def wait_for_node_status(node, status=True, wait_timeout=TIMEOUT_1MIN):
    """Wait for node status Ready (status=True) or NotReady (status=False)"""
    for sample in TimeoutSampler(wait_timeout=wait_timeout, sleep=1, func=lambda: node.kubelet_ready):
        if (status and sample) or (not status and not sample):
            return


def utility_daemonset_for_custom_tests(
    generated_pulled_secret,
    cnv_tests_utilities_service_account,
    label,
    node_selector_label=None,
    delete_pod_resources_limit=False,
):
    """
    Deploy modified utility daemonset into the kube-system namespace.

    Args:
        generated_pulled_secret (str): fixture that contains the generated pulled secret.
        cnv_tests_utilities_service_account (ServiceAccount): fixture that contains the service account
        for CNV tests utilities.
        label (str): string that is used as a label for the daemonset.
        node_selector_label (dict):  dictionary that contains the node selector for the daemonset. This is an optional
        parameter and if not provided, no node selector will be set.
        delete_pod_resources_limit (bool): boolean that indicates whether the pod resources
        limit should be deleted or not.

    Returns:
        DaemonSet: DaemonSet object.
    """
    ds_yaml_file = get_daemonset_yaml_file_with_image_hash(
        generated_pulled_secret=generated_pulled_secret,
        service_account=cnv_tests_utilities_service_account,
    )

    ds_yaml = yaml.safe_load(ds_yaml_file.read())
    ds_yaml_spec = ds_yaml["spec"]
    ds_yaml_metadata = ds_yaml["metadata"]

    if node_selector_label:
        ds_yaml_spec["template"]["spec"]["nodeSelector"] = node_selector_label
    if delete_pod_resources_limit:
        del ds_yaml["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]

    ds_yaml_metadata["labels"]["cnv-test"] = label
    ds_yaml_metadata["name"] = label

    ds_yaml_spec["selector"]["matchLabels"]["cnv-test"] = label
    ds_yaml_spec["template"]["metadata"]["labels"]["cnv-test"] = label
    ds_yaml_spec["template"]["spec"]["containers"][0]["name"] = label

    ds_yaml_file = io.StringIO(yaml.dump(ds_yaml))

    with DaemonSet(yaml_file=ds_yaml_file) as ds:
        ds.wait_until_deployed()
        yield ds


def login_with_token(api_address, token):
    """
    Log in to an OpenShift cluster using a token.

    Args:
        api_address (str): The API address of the OpenShift cluster.
        token (str): The authentication token.

    Returns:
        bool: True if login is successful, False otherwise.
    """
    login_command = f"oc login {api_address} --token {token}"
    return login_to_account(login_command=login_command)


def login_with_user_password(api_address, user, password=None):
    """
    Log in to an OpenShift cluster using a username and password.

    Args:
        api_address (str): The API address of the OpenShift cluster.
        user (str): Cluster's username
        password (str, optional): Cluster's password

    Returns:
        bool: True if login is successful otherwise False.
    """
    login_command = f"oc login {api_address} -u {user}"
    if password:
        login_command += f" -p {password}"
    return login_to_account(login_command=login_command)


def login_to_account(login_command):
    """
    Log in to an OpenShift cluster using a given login command.

    Args:
        login_command (str): The full login command.

    Returns:
        bool: True if login is successful, False otherwise.
    """
    stop_errors = [
        "connect: no route to host",
        "x509: certificate signed by unknown authority",
    ]

    samples = TimeoutSampler(
        wait_timeout=60,
        sleep=3,
        exceptions_dict={CalledProcessError: []},
        func=Popen,
        args=login_command,
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
    )

    login_result = None

    try:
        LOGGER.info("Trying to login to account")
        for sample in samples:
            login_result = sample.communicate()
            login_decoded_result = login_result[1].decode("utf-8")
            if sample.returncode == 0:
                LOGGER.info("Login - success")
                return True

            if any(err in login_decoded_result for err in stop_errors):
                break

    except TimeoutExpiredError:
        if login_result:
            LOGGER.warning(
                f"Login - failed due to the following error: {login_result[0].decode('utf-8')} {login_decoded_result}"
            )
        return False


def get_resources_by_name_prefix(prefix, namespace, api_resource_name):
    """
    Args:
        prefix (str): str
        namespace (str): Namespace name.
        api_resource_name (str): API Object name

    Returns:
         A list of all matching objects in the given resource
    """
    return [
        resource_object
        for resource_object in api_resource_name.get(namespace=namespace)
        if resource_object.name.startswith(prefix)
    ]


@cache
def get_infrastructure(admin_client: DynamicClient) -> Infrastructure:
    return Infrastructure(client=admin_client, name=CLUSTER, ensure_exists=True)


def get_cluster_platform(admin_client: DynamicClient) -> str:
    return get_infrastructure(admin_client=admin_client).instance.status.platform


def query_version_explorer(api_end_point: str, query_string: str) -> Any:
    try:
        response = requests.get(
            url=f"{py_config['version_explorer_url']}/{api_end_point}?{query_string}",
            verify=False,
            timeout=TIMEOUT_30SEC,
        )
        response.raise_for_status()
    except (HTTPError, ConnectionError, Timeout, TooManyRedirects) as ex:
        LOGGER.warning(f"Error occurred: {ex}")
        return None
    return response.json()


def wait_for_version_explorer_response(api_end_point: str, query_string: str) -> Any:
    version_explorer_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_30SEC,
        func=query_version_explorer,
        api_end_point=api_end_point,
        query_string=query_string,
    )
    for sample in version_explorer_sampler:
        if sample:
            return sample


def stable_channel_released_to_prod(channels: list[dict[str, str | bool]]) -> bool:
    return any(item.get("channel") == "stable" and item.get("released_to_prod") for item in channels)


def get_latest_stable_released_z_stream_info(minor_version: str) -> dict[str, str] | None:
    builds = wait_for_version_explorer_response(
        api_end_point="GetBuildsWithErrata",
        query_string=f"minor_version={minor_version}",
    )["builds"]

    latest_z_stream = None
    for build in builds:
        if build["errata_status"] == "SHIPPED_LIVE" and stable_channel_released_to_prod(channels=build["channels"]):
            build_version = Version(version=build["csv_version"])
            if latest_z_stream:
                if build_version > latest_z_stream:
                    latest_z_stream = build_version
            else:
                latest_z_stream = build_version
    return get_build_info_dict(version=str(latest_z_stream)) if latest_z_stream else None


def get_cnv_info_by_iib(iib: str) -> dict[str, str]:
    build_info = wait_for_version_explorer_response(
        api_end_point="GetBuildByIIB",
        query_string=f"iib_number={iib}",
    )
    return get_build_info_dict(
        version=str(Version(build_info["cnv_version"].split(".rhel9")[0])),
        channel=build_info["channel"],
    )


def get_build_info_dict(version: str, channel: str = "stable") -> dict[str, str]:
    return {
        "version": version,
        "channel": channel,
    }


def get_deployment_by_name(namespace_name, deployment_name):
    """
    Gets a deployment object by name

    Args:
        namespace_name (str): name of the associated namespace
        deployment_name (str): Name of the deployment

    Returns:
        Deployment: Deployment object
    """
    deployment = Deployment(
        namespace=namespace_name,
        name=deployment_name,
    )
    if deployment.exists:
        return deployment
    raise ResourceNotFoundError(f"Deployment: {deployment_name} is not found in namespace: {namespace_name}")


def get_prometheus_k8s_token(duration="1800s"):
    token_command = f"oc create token {PROMETHEUS_K8S} -n {NamespacesNames.OPENSHIFT_MONITORING} --duration={duration}"
    command_success, out, _ = run_command(command=shlex.split(token_command), verify_stderr=False)
    assert command_success, f"Command {token_command} failed to execute"
    return out


def get_artifactory_header():
    return {"Authorization": f"Bearer {os.environ['ARTIFACTORY_TOKEN']}"}


def get_artifactory_secret(
    namespace,
):
    artifactory_secret = Secret(
        name=ARTIFACTORY_SECRET_NAME,
        namespace=namespace,
        accesskeyid=base64_encode_str(os.environ["ARTIFACTORY_USER"]),
        secretkey=base64_encode_str(os.environ["ARTIFACTORY_TOKEN"]),
    )
    if not artifactory_secret.exists:
        artifactory_secret.deploy()
    return artifactory_secret


def get_artifactory_config_map(
    namespace,
):
    artifactory_cm = ConfigMap(
        name="artifactory-configmap",
        namespace=namespace,
        data={"tlsregistry.crt": ssl.get_server_certificate(addr=(py_config["server_url"], 443))},
    )
    if not artifactory_cm.exists:
        artifactory_cm.deploy()
    return artifactory_cm


def cleanup_artifactory_secret_and_config_map(artifactory_secret=None, artifactory_config_map=None):
    if artifactory_secret:
        artifactory_secret.clean_up()
    if artifactory_config_map:
        artifactory_config_map.clean_up()


def add_scc_to_service_account(namespace, scc_name, sa_name):
    output = subprocess.check_output(
        shlex.split(f"oc adm policy add-scc-to-user {scc_name} system:serviceaccount:{namespace}:{sa_name}")
    )
    if f'added: "{sa_name}"' not in str(output):
        raise AssertionError(f"Unable to add {sa_name} to {scc_name} scc")


def get_node_selector_name(node_selector):
    return node_selector[f"{Resource.ApiGroup.KUBERNETES_IO}/hostname"]


def get_node_selector_dict(node_selector):
    return {f"{Resource.ApiGroup.KUBERNETES_IO}/hostname": node_selector}


def get_nodes_cpu_model(nodes):
    """
    Checks the cpu model labels on each nodes passed and returns a dictionary of nodes and supported nodes

    :param nodes (list) : Nodes, for which cpu model labels are to be checked

    :return: Dict of nodes and associated cpu models
    """

    nodes_cpu_model = {"common": {}, "modern": {}}
    for node in nodes:
        nodes_cpu_model["common"][node.name] = set()
        nodes_cpu_model["modern"][node.name] = set()
        for label, value in node.labels.items():
            match_object = re.match(rf"{CPU_MODEL_LABEL_PREFIX}/(.*)", label)
            if is_cpu_model_not_in_excluded_list(
                filter_list=EXCLUDED_CPU_MODELS, match=match_object, label_value=value
            ):
                nodes_cpu_model["common"][node.name].add(match_object.group(1))
            if is_cpu_model_not_in_excluded_list(
                filter_list=EXCLUDED_OLD_CPU_MODELS, match=match_object, label_value=value
            ):
                nodes_cpu_model["modern"][node.name].add(match_object.group(1))
    return nodes_cpu_model


def is_cpu_model_not_in_excluded_list(filter_list, match, label_value):
    return bool(match and label_value == "true" and not any(element in match.group(1) for element in filter_list))


def get_host_model_cpu(nodes):
    nodes_host_model_cpu = {}
    for node in nodes:
        for label, value in node.labels.items():
            match_object = re.match(rf"{HOST_MODEL_CPU_LABEL}/(.*)", label)
            if match_object and value == "true":
                nodes_host_model_cpu[node.name] = match_object.group(1)
    assert len(nodes_host_model_cpu) == len(nodes), (
        f"All nodes did not have host-model-cpu label: {nodes_host_model_cpu} "
    )
    return nodes_host_model_cpu


def find_common_cpu_model_for_live_migration(cluster_cpu, host_cpu_model):
    if cluster_cpu:
        if len(set(host_cpu_model.values())) == 1:
            LOGGER.info(f"Host model cpus for all nodes are same {host_cpu_model}. No common cpus are needed")
            return None
        else:
            LOGGER.info(f"Using cluster node cpu: {cluster_cpu}")
            return cluster_cpu
    # if we reach here, it is heterogeneous cluster, we would return None
    LOGGER.warning("This is a heterogeneous cluster with no common cluster cpu.")
    return None


def get_common_cpu_from_nodes(cluster_cpus):
    """
    Receives a set of unique common cpus between all the schedulable nodes and returns one from the set
    """
    return next(iter(cluster_cpus)) if cluster_cpus else None


def delete_resources_from_namespace_by_type(resources_types, namespace, wait=False):
    for resource_type in resources_types:
        for resource in list(resource_type.get(namespace=namespace)):
            resource.delete(wait=wait)


def get_linux_guest_agent_version(ssh_exec):
    ssh_exec.sudo = True
    return guest_agent_version_parser(version_string=ssh_exec.package_manager.info("qemu-guest-agent"))


def get_linux_os_info(ssh_exec):
    # Use guest agent version without the build number
    ga_ver = get_linux_guest_agent_version(ssh_exec=ssh_exec).split("-")[0]
    hostname = ssh_exec.network.hostname
    os_release = ssh_exec.os.release_info
    kernel = ssh_exec.os.kernel_info
    timezone = ssh_exec.os.timezone

    return {
        "guestAgentVersion": ga_ver,
        "hostname": hostname,
        "os": {
            "name": os_release["NAME"],
            "kernelRelease": kernel.release,
            "version": os_release["VERSION"],
            "prettyName": os_release["PRETTY_NAME"],
            "versionId": os_release["VERSION_ID"],
            "kernelVersion": kernel.version,
            "machine": kernel.type,
            "id": os_release["ID"],
        },
        "timezone": f"{timezone.name}, {int(timezone.offset) * 36}",
    }


def validate_os_info_vmi_vs_linux_os(vm: utilities.virt.VirtualMachineForTests) -> None:
    vmi_info = utilities.virt.get_guest_os_info(vmi=vm.vmi)
    linux_info = get_linux_os_info(ssh_exec=vm.ssh_exec)["os"]

    assert vmi_info == linux_info, f"Data mismatch! VMI: {vmi_info}\nOS: {linux_info}"


def get_nodes_cpu_architecture(nodes: list[Node]) -> str:
    nodes_cpu_arch = {node.labels[KUBERNETES_ARCH_LABEL] for node in nodes}
    assert len(nodes_cpu_arch) == 1, "Mixed CPU architectures in the cluster is not supported"
    return next(iter(nodes_cpu_arch))
