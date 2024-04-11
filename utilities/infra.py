import http
import io
import logging
import os
import platform
import re
import shlex
import tarfile
import stat
import zipfile

import netaddr

import pytest
import requests
import urllib3
from kubernetes.client import ApiException
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.console_cli_download import ConsoleCLIDownload
from ocp_resources.namespace import Namespace
from kubernetes.dynamic.exceptions import ResourceNotFoundError, NotFoundError

from ocp_resources.pod import Pod
from ocp_utilities.exceptions import NodeUnschedulableError, NodeNotReadyError
from ocp_utilities.infra import (
    assert_nodes_in_healthy_condition,
    assert_nodes_schedulable,
    get_client,
)
from utilities.constants import (
    KUBELET_READY_CONDITION,
    IMAGE_CRON_STR,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
    TIMEOUT_1MIN,
    AMD_64,
)
from utilities.exceptions import (
    ClusterSanityError,
    UtilityPodNotFoundError,
    UrlNotFoundError,
)
from utilities.hco import assert_hyperconverged_health, get_hyperconverged_resource
from pyhelper_utils.shell import run_command

LOGGER = logging.getLogger(__name__)


def get_namespace(name):
    namespace = Namespace(name=name)
    if namespace.exists:
        return namespace
    raise ResourceNotFoundError(f"Namespace: {name} not found")


def cluster_sanity(
    admin_client,
    nodes,
    hco_namespace,
):
    LOGGER.info("Running cluster sanity.")
    try:
        LOGGER.info("Check nodes sanity.")
        assert_nodes_in_healthy_condition(
            nodes=nodes, healthy_node_condition_type=KUBELET_READY_CONDITION
        )
        assert_nodes_schedulable(nodes=nodes)

        try:
            wait_for_pods_running(
                admin_client=admin_client,
                namespace_name=hco_namespace,
                filter_pods_by_name=IMAGE_CRON_STR,
            )
        except TimeoutExpiredError as timeout_error:
            LOGGER.error(timeout_error)
            raise ClusterSanityError(
                err_str=f"Timed out waiting for all pods in namespace {hco_namespace} to get to running state."
            )

        assert_hyperconverged_health(
            hyperconverged=get_hyperconverged_resource(namespace_name=hco_namespace),
            system_health_status="healthy",
        )
    except (ClusterSanityError, NodeUnschedulableError, NodeNotReadyError) as ex:
        pytest.exit(reason=str(ex), returncode=99)


def wait_for_pods_running(
    admin_client,
    namespace_name,
    number_of_consecutive_checks=1,
    filter_pods_by_name=None,
):
    """
    Waits for all pods in a given namespace to reach Running/Completed state. To avoid catching all pods in running
    state too soon, use number_of_consecutive_checks with appropriate values.
    Args:
         admin_client(DynamicClient): Dynamic client
         namespace_name(str): name of a namespace
         number_of_consecutive_checks(int): Number of times to check for all pods in running state
         filter_pods_by_name(str): string to filter pod names by
    Raises:
        TimeoutExpiredError: Raises TimeoutExpiredError if any of the pods in the given namespace are not in Running
         state
    """
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
        func=get_not_running_pods,
        pods=list(Pod.get(dyn_client=admin_client, namespace=namespace_name)),
        filter_pods_by_name=filter_pods_by_name,
    )
    sample = None
    try:
        current_check = 0
        for sample in samples:
            if not sample:
                current_check += 1
                if current_check >= number_of_consecutive_checks:
                    return True
            else:
                current_check = 0
    except TimeoutExpiredError:
        if sample:
            LOGGER.error(
                f"timeout waiting for all pods in namespace {namespace_name} to reach "
                f"running state, following pods are in not running state: {sample}"
            )
            raise


def get_pod_container_error_status(pod):
    pod_instance_status = pod.instance.status
    # Check the containerStatuses and if any containers is in waiting state, return that information:

    for container_status in pod_instance_status.get("containerStatuses", []):
        waiting_container = container_status.get("state", {}).get("waiting")
        if waiting_container:
            return (
                waiting_container["reason"]
                if waiting_container.get("reason")
                else waiting_container
            )


def get_not_running_pods(pods, filter_pods_by_name=None):
    pods_not_running = []
    for pod in pods:
        pod_instance = pod.instance
        if filter_pods_by_name and filter_pods_by_name in pod.name:
            LOGGER.warning(f"Ignoring pod: {pod.name} for pod state validations.")
            continue
        container_status_error = get_pod_container_error_status(pod=pod)
        if container_status_error:
            pods_not_running.append({pod.name: container_status_error})
        try:
            # Waits for all pods in a given namespace to be in final healthy state(running/completed).
            # We also need to keep track of pods marked for deletion as not running. This would ensure any
            # pod that was spinned up in place of pod marked for deletion, reaches healthy state before end
            # of this check
            if pod_instance.metadata.get(
                "deletionTimestamp"
            ) or pod_instance.status.phase not in (
                pod.Status.RUNNING,
                pod.Status.SUCCEEDED,
            ):
                pods_not_running.append({pod.name: pod.status})
        except (ResourceNotFoundError, NotFoundError):
            LOGGER.warning(
                f"Ignoring pod {pod.name} that disappeared during cluster sanity check"
            )
            pods_not_running.append({pod.name: "Deleted"})
    return pods_not_running


def run_virtctl_command(command, virtctl_binary="virtctl", namespace=None, check=False):
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
    kubeconfig = os.getenv("KUBECONFIG")
    if namespace:
        virtctl_cmd.extend(["-n", namespace])

    if kubeconfig:
        virtctl_cmd.extend(["--kubeconfig", kubeconfig])

    virtctl_cmd.extend(command)
    res, out, err = run_command(command=virtctl_cmd, check=check)

    return res, out, err


def get_clusterversion(dyn_client):
    for cvo in ClusterVersion.get(dyn_client=dyn_client):
        return cvo


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
        return self.pod.execute(
            command=_command, ignore_rc=ignore_rc, timeout=timeout
        ).strip()

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


def get_console_spec_links(admin_client, name):
    console_cli_download_resource_content = ConsoleCLIDownload(
        name=name, client=admin_client
    )
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


def get_machine_platform():
    os_machine_type = platform.machine()
    return AMD_64 if os_machine_type == "x86_64" else os_machine_type


def download_and_extract_file_from_cluster(tmpdir, url):
    zip_file_extension = ".zip"
    LOGGER.info(f"Downloading archive: url={url}")
    urllib3.disable_warnings()  # TODO: remove this when we fix the SSL warning
    response = requests.get(url, verify=False)
    assert (
        response.status_code == http.HTTPStatus.OK
    ), f"Response status code: {response.status_code}"
    archive_file_data = io.BytesIO(initial_bytes=response.content)
    LOGGER.info("Extract the archive")
    if url.endswith(zip_file_extension):
        archive_file_object = zipfile.ZipFile(file=archive_file_data)
    else:
        archive_file_object = tarfile.open(fileobj=archive_file_data, mode="r")
    archive_file_object.extractall(path=tmpdir)
    extracted_filenames = (
        archive_file_object.namelist()
        if url.endswith(zip_file_extension)
        else archive_file_object.getnames()
    )
    return [os.path.join(tmpdir.strpath, namelist) for namelist in extracted_filenames]


def get_and_extract_file_from_cluster(urls, system_os, dest_dir, machine_type=None):
    if not machine_type:
        machine_type = get_machine_platform()
    for url in urls:
        if system_os in url and machine_type in url:
            extracted_files = download_and_extract_file_from_cluster(
                tmpdir=dest_dir, url=url
            )
            assert (
                len(extracted_files) == 1
            ), f"Only a single file expected in archive: extracted_files={extracted_files}"
            return extracted_files[0]

    raise UrlNotFoundError(f"Url not found for system_os={system_os}")


def download_file_from_cluster(get_console_spec_links_name, dest_dir):
    console_cli_links = get_console_spec_links(
        admin_client=get_client(),
        name=get_console_spec_links_name,
    )
    download_urls = get_all_console_links(
        console_cli_downloads_spec_links=console_cli_links
    )
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
