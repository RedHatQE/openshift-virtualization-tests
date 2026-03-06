import http
import json
import logging
import multiprocessing
import random
import threading
import time
from contextlib import contextmanager
from datetime import datetime

from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.node import Node
from ocp_resources.pod import Pod
from ocp_resources.service import Service
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler, TimeoutWatch

from utilities.constants import (
    DEFAULT_HCO_CONDITIONS,
    MIGRATION_POLICY_VM_LABEL,
    PORT_80,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_10SEC,
    TIMEOUT_30MIN,
    TIMEOUT_30SEC,
)
from utilities.data_collector import write_to_file
from utilities.infra import (
    ExecCommandOnPod,
    get_daemonsets,
    get_deployments,
    get_hco_mismatch_statuses,
    get_hyperconverged_resource,
    get_pod_by_name_prefix,
    get_pods,
    get_resources_by_name_prefix,
    wait_for_node_status,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm, wait_for_running_vm

LOGGER = logging.getLogger(__name__)


def create_pod_deleting_process(
    client,
    pod_prefix,
    namespace_name,
    ratio,
    interval=TIMEOUT_5SEC,
    max_duration=TIMEOUT_1MIN,
):
    """
    Creates a process that, when started,
    continuously deletes pods for a certain amount of time or until the process is stopped.

    Args:
        client (DynamicClient)
        pod_prefix (str): Pod name prefix used to find the pods to be deleted.
        namespace_name (str): Name of the namespace were the pods to be deleted live.
        ratio (float): Percentage of pods to be deleted (expressed as a fraction between 0 and 1).
        interval (int): Interval that determines how often the pods will be deleted.
        max_duration (int): Maximum time that the process will be running.

    Returns:
        multiprocessing.Process: Process that continuously deletes pods.
    """

    def _delete_pods_continuously(client, pod_prefix, namespace_name, ratio, interval, max_duration):
        try:
            for _ in TimeoutSampler(
                wait_timeout=max_duration,
                sleep=interval,
                func=delete_pods,
                client=client,
                pod_prefix=pod_prefix,
                namespace_name=namespace_name,
                ratio=ratio,
            ):
                pass
        except TimeoutExpiredError:
            LOGGER.info("Pod deleting process finished.")

    return multiprocessing.Process(
        name="pod_delete",
        target=_delete_pods_continuously,
        args=(
            client,
            pod_prefix,
            namespace_name,
            ratio,
            interval,
            max_duration,
        ),
    )


def create_nginx_monitoring_process(
    url: str,
    curl_timeout: int,
    sampling_duration: int,
    sampling_interval: int,
    utility_pods: list[Pod],
    control_plane_host_node: Node,
) -> multiprocessing.process.BaseProcess:
    """
    Creates a process that, when started,
    Continuously queries the HTTP server that runs on the VM. Runs for the duration defined
    in 'sampling_duration' or until interrupted.

    Args:
        url (str): The url of the http server.
        curl_timeout (int): timeout in seconds for curl connect-timeout parameter.
        sampling_duration (str): The amount of time during which sampling will take place.
        sampling_interval (int): Interval that determines how often the http server will be queried.
        utility_pods (list): list of utility pods
        control_plane_host_node (Node): control plane node

    Returns:
        multiprocessing.Process: Process that continuously query the http server.
    """

    def _monitor_nginx_server(
        _url,
        _curl_timeout,
        _sampling_duration,
        _sampling_interval,
        _utility_pods,
        _control_plane_host_node,
    ):
        timeout_watch = TimeoutWatch(timeout=_sampling_duration)
        while timeout_watch.remaining_time() > 0:
            if not is_http_ok(utility_pods=_utility_pods, node=_control_plane_host_node, url=_url):
                raise Exception("Wrong status code from server.")
            time.sleep(_sampling_interval)
        LOGGER.info("HTTP querying finished successfully.")

    return multiprocessing.Process(
        name="nginx_monitoring",
        target=_monitor_nginx_server,
        args=(
            url,
            curl_timeout,
            sampling_duration,
            sampling_interval,
            utility_pods,
            control_plane_host_node,
        ),
    )


def get_pods_status(admin_client, namespaces):
    pods_status = {"pod_status": {}}
    for namespace in namespaces:
        pods = get_pods(client=admin_client, namespace=namespace)
        pods_status["pod_status"][namespace.name] = {}
        for pod in pods:
            # Set the log level to ERROR to avoid cluttering the console
            with resource_log_level_error(resource=pod) as _pod:
                pods_status["pod_status"][namespace.name][_pod.name] = _pod.status

    return pods_status


def get_deployment_replicas(admin_client, namespaces):
    deployments_replicas = {"deployment_replicas": {}}
    for namespace in namespaces:
        deployments = get_deployments(admin_client=admin_client, namespace=namespace.name)
        deployments_replicas["deployment_replicas"][namespace.name] = {}
        for deployment in deployments:
            # Set the log level to ERROR to avoid cluttering the console
            with resource_log_level_error(resource=deployment) as _deployment:
                deployment_instance = _deployment.instance
                deployments_replicas["deployment_replicas"][namespace.name][_deployment.name] = {
                    "desired": deployment_instance.spec.replicas,
                    "available": deployment_instance.status.availableReplicas,
                }

    return deployments_replicas


def get_daemonset_replicas(admin_client, namespaces):
    daemonsets_replicas = {"daemonset_replicas": {}}
    for namespace in namespaces:
        daemonsets = get_daemonsets(admin_client=admin_client, namespace=namespace.name)
        daemonsets_replicas["daemonset_replicas"][namespace.name] = {}
        for daemonset in daemonsets:
            # Set the log level to ERROR to avoid cluttering the console
            with resource_log_level_error(resource=daemonset) as _daemonset:
                daemonset_instance = _daemonset.instance
                daemonsets_replicas["daemonset_replicas"][namespace.name][_daemonset.name] = {
                    "desired": daemonset_instance.status.desiredNumberScheduled,
                    "ready": daemonset_instance.status.numberReady,
                }

    return daemonsets_replicas


def get_nodes_status():
    nodes_status = {"nodes": {}}
    for node in Node.get():
        # Set loglevel to ERROR to avoid cluttering with the logs resulting from getting node status
        with resource_log_level_error(resource=node) as _node:
            nodes_status["nodes"][node.name] = "ready" if _node.kubelet_ready else "not ready"

    return nodes_status


def get_hyperconverged_status_conditions(client, hco_namespace):
    hco_instance = get_hyperconverged_resource(client=client, hco_ns_name=hco_namespace.name).instance
    hco_status_summary = (
        "OK" if not get_hco_mismatch_statuses(hco_instance.status.conditions, DEFAULT_HCO_CONDITIONS) else "NOK"
    )

    return {
        "hco_status": {
            "summary": hco_status_summary,
            "hco_status_conditions": hco_instance.to_dict()["status"]["conditions"],
        }
    }


def collect_cluster_health_info(client, hco_namespace, additional_namespaces):
    namespaces_to_monitor = additional_namespaces + [hco_namespace]
    pods_status = get_pods_status(admin_client=client, namespaces=namespaces_to_monitor)
    deployments_replicas = get_deployment_replicas(admin_client=client, namespaces=namespaces_to_monitor)
    daemonset_replicas = get_daemonset_replicas(admin_client=client, namespaces=namespaces_to_monitor)
    nodes_status = get_nodes_status()
    hco_status_conditions = get_hyperconverged_status_conditions(client=client, hco_namespace=hco_namespace)

    log_content = json.dumps(
        {
            f"{datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S')}": [
                pods_status,
                deployments_replicas,
                daemonset_replicas,
                nodes_status,
                hco_status_conditions,
            ]
        },
        indent=4,
    )

    write_to_file(
        file_name="chaos-monitoring.txt",
        content=f"{log_content}\n",
        base_directory=py_config["data_collector"]["collector_directory"],
        mode="a",
    )


def create_cluster_monitoring_process(
    client,
    hco_namespace,
    additional_namespaces,
    interval=TIMEOUT_10SEC,
    max_duration=TIMEOUT_30MIN,
):
    def _monitor_cluster():
        timeout_watch = TimeoutWatch(timeout=max_duration)
        while timeout_watch.remaining_time() > 0:
            collect_cluster_health_info(
                client=client,
                hco_namespace=hco_namespace,
                additional_namespaces=additional_namespaces,
            )
            time.sleep(interval)

    return multiprocessing.Process(
        name="cluster_monitoring",
        target=_monitor_cluster,
    )


def terminate_process(process):
    if process.is_alive():
        LOGGER.info(f"Terminating process: {process.name}")
        process.kill()


@contextmanager
def resource_log_level_error(resource):
    resource.logger.setLevel(level=logging.ERROR)
    yield resource
    resource.logger.setLevel(level=logging.INFO)


def create_vm_with_nginx_service(chaos_namespace, admin_client, utility_pods, node, node_selector_label=None):
    name = "nginx"
    with VirtualMachineForTests(
        namespace=chaos_namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        client=admin_client,
        node_selector_labels=node_selector_label,
        additional_labels=MIGRATION_POLICY_VM_LABEL,
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
        vm.custom_service_enable(service_name=name, port=PORT_80, service_type=Service.Type.CLUSTER_IP)
        verify_vm_service_reachable(
            utility_pods=utility_pods,
            node=node,
            url=f"{vm.custom_service.instance.spec.clusterIPs[0]}:{PORT_80}",
        )
        LOGGER.info(f"VMI Host Node:{vm.vmi.node.name}")
        yield vm


def verify_vm_service_reachable(utility_pods, node, url):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
            func=is_http_ok,
            utility_pods=utility_pods,
            node=node,
            url=url,
        ):
            if sample:
                break
    except TimeoutExpiredError:
        LOGGER.error(f"Service at {url} is not reachable")
        raise


def is_http_ok(utility_pods, node, url):
    http_result = ExecCommandOnPod(utility_pods=utility_pods, node=node).exec(
        command=f"curl -s --connect-timeout {TIMEOUT_10SEC} -w '%{{http_code}}' {url}  -o /dev/null"
    )
    return int(http_result) == http.HTTPStatus.OK


def rebooting_node(node, utility_pods):
    LOGGER.info(f"Rebooting node {node.name}")
    ExecCommandOnPod(utility_pods=utility_pods, node=node).exec(command="shutdown -r", ignore_rc=True)
    wait_for_node_status(node=node, status=False, wait_timeout=TIMEOUT_5MIN)
    yield node
    wait_for_node_status(node=node, status=True, wait_timeout=TIMEOUT_10MIN)


def pod_deleting_process_recover(resources, namespace, pod_prefix):
    """
    Wait for affected workloads to recover after pod deletion.

    This helper ensures that pods belonging to the given Kubernetes workloads
    (Deployment or DaemonSet) recover after a pod-deleting test. The function
    polls the workloads until they report a healthy state.

    Args:
        resources (list[Union[Deployment, DaemonSet]]):
            A list of Deployment/DaemonSet resource types to be checked.
        namespace (str):
            Namespace in which the workloads reside.
        pod_prefix (str):
            Name prefix used to locate affected workloads.

    Raises:
        ValueError:
            If any resource is not a Deployment or DaemonSet.
        ResourceNotFoundError:
            If no matching workloads are found in the given namespace.
    """
    if not isinstance(resources, list):
        raise TypeError("resources must be a list of Deployment or DaemonSet")

    for resource in resources:
        if resource.kind not in (Deployment.kind, DaemonSet.kind):
            raise ValueError(
                f"Unsupported resource type {resource.kind} for pod recovery. "
                "Only Deployment or DaemonSet is supported."
            )

    found_any = False

    for resource in resources:
        resource_objs = get_resources_by_name_prefix(
            prefix=pod_prefix,
            namespace=namespace,
            api_resource_name=resource,
        )
        if not resource_objs:
            LOGGER.info(f"No {resource.kind} found with prefix {pod_prefix} in namespace {namespace}")
            continue

        found_any = True

        for resource_obj in resource_objs:
            LOGGER.info(f"Waiting for {resource.kind} {resource_obj.name} to recover")
            if resource is Deployment:
                resource_obj.wait_for_replicas()
            elif resource is DaemonSet:
                resource_obj.wait_until_deployed()
            else:
                raise ValueError(f"Unsupported resource type {resource} passed to pod_deleting_process_recover")

    if found_any:
        LOGGER.info("Pod recovery process completed successfully.")
    else:
        raise ResourceNotFoundError(f"No resources found with prefix {pod_prefix} in namespace {namespace}")


def get_instance_type(name):
    """
    Function to check if the instance type exists
    """
    instance_type = VirtualMachineClusterInstancetype(name=name)
    if not instance_type.exists:
        raise ResourceNotFoundError(f"Required instance type {name} does not exist")
    return instance_type


def delete_pods(client, pod_prefix, namespace_name, ratio):
    """Delete a ratio of pods matching the given prefix in a namespace.

    This function lists all pods whose names start with ``pod_prefix`` in the
    specified namespace, randomly selects a subset based on ``ratio``,
    deletes them, and waits for deletion.

    Args:
        client: OpenShift/Kubernetes client used to query and delete pods.
        pod_prefix (str): Prefix of pod names to match.
        namespace_name (str): Namespace where pods are located.
        ratio (float): Fraction of pods to delete (0 <= ratio <= 1). If ratio is 0, no pods are deleted.

    Raises:
        ResourceNotFoundError: If no matching pods are found.
    """
    if ratio <= 0:
        LOGGER.info(f"Ratio is {ratio}, skipping pod deletion for prefix {pod_prefix}")
        return

    pods = get_pod_by_name_prefix(
        client=client,
        pod_prefix=pod_prefix,
        namespace=namespace_name,
        get_all=True,
    )

    if not pods:
        LOGGER.error(f"No pods found with prefix {pod_prefix} in namespace {namespace_name}")
        raise ResourceNotFoundError(f"No pods found with prefix {pod_prefix} in namespace {namespace_name}")

    delete_count = max(1, round(ratio * len(pods)))
    pods_to_delete = random.sample(population=pods, k=min(delete_count, len(pods)))

    LOGGER.info(f"Deleting {len(pods_to_delete)} out of {len(pods)} pods: {[pod.name for pod in pods_to_delete]}")

    for pod in pods_to_delete:
        LOGGER.info(f"Deleting pod {pod.name}")
        pod.clean_up()

        try:
            pod.wait_deleted(timeout=TIMEOUT_30SEC)
        except TimeoutExpiredError:
            LOGGER.warning(f"Pod {pod.name} was not deleted")


def delete_pods_continuously(
    stop_event,
    client,
    pod_prefix,
    namespace_name,
    ratio,
    interval,
    max_duration,
):
    """Continuously delete pods until stopped or max duration is reached.

    This function repeatedly deletes pods matching ``pod_prefix`` every
    ``interval`` seconds until either ``stop_event`` is set or
    ``max_duration`` is exceeded.

    Intended to be executed in a background thread.

    Args:
        stop_event (threading.Event): Event used to signal termination.
        client: OpenShift/Kubernetes client.
        pod_prefix (str): Prefix of pod names to match.
        namespace_name (str): Namespace where pods are located.
        ratio (float): Fraction of pods to delete each iteration.
        interval (int): Seconds to wait between deletion rounds.
        max_duration (int): Maximum total runtime in seconds.
    """
    start_time = time.time()

    while not stop_event.is_set():
        if time.time() - start_time > max_duration:
            LOGGER.info("Pod deleting process finished (max_duration reached)")
            break

        try:
            delete_pods(
                client=client,
                pod_prefix=pod_prefix,
                namespace_name=namespace_name,
                ratio=ratio,
            )
        except ResourceNotFoundError:
            LOGGER.info(f"No pods found with prefix {pod_prefix} in this iteration")
        # Using stop_event.wait() intentionally to support cooperative thread cancellation via threading.Event.
        # Because TimeoutSampler doesn't support threading.Event based shutdown.
        stop_event.wait(timeout=interval)


def create_pod_deleting_thread(
    client,
    pod_prefix,
    namespace_name,
    ratio,
    interval=TIMEOUT_5SEC,
    max_duration=TIMEOUT_1MIN,
):
    """Create a background thread for continuous pod deletion.

    The returned thread is configured but NOT started. Call ``thread.start()``
    to begin deleting pods. Pod deletion can be stopped by calling
    ``stop_event.set()``.

    Args:
        client: OpenShift/Kubernetes client.
        pod_prefix (str): Prefix of pod names to match.
        namespace_name (str): Namespace where pods are located.
        ratio (float): Fraction of pods to delete each iteration.
        interval (int, optional): Seconds between deletion rounds.
        max_duration (int, optional): Maximum total runtime in seconds.

    Returns:
        tuple:
            threading.Thread: Daemon thread executing pod deletion.
            threading.Event: Event used to signal the thread to stop.
    """
    stop_event = threading.Event()

    thread = threading.Thread(
        name="pod_delete",
        target=delete_pods_continuously,
        args=(
            stop_event,
            client,
            pod_prefix,
            namespace_name,
            ratio,
            interval,
            max_duration,
        ),
        daemon=True,
    )

    return thread, stop_event


def wait_for_restored_vm(
    admin_client,
    namespace,
    vm_name_prefix,
    timeout=TIMEOUT_5MIN,
    sleep=5,
):
    """
    Wait for a restored VirtualMachine to appear, stabilize, and reach Running state.

    This helper performs a multi-stage wait for a VirtualMachine recreated by OADP restore:

    1. Polls until a VM with the given name prefix appears in the namespace.
    2. Waits for the VM to become stable (i.e., no longer temporarily disappearing due to
       reconciliation or recreation).
    3. Waits until the VM reaches the Running phase.

    The returned object is wrapped as a ``VirtualMachineForTests`` instance. This function
    has side effects, including polling the Kubernetes API, invoking ``wait_for_running_vm()``,
    and logging intermediate VM states.

    Args:
        admin_client:
            OpenShift/Kubernetes client used to query VM resources.
        namespace (str):
            Namespace where the restored VM is expected to appear.
        vm_name_prefix (str):
            Prefix of the restored VM name.
        timeout (int, optional):
            Total timeout in seconds for each waiting stage. Defaults to ``TIMEOUT_5MIN``.
        sleep (int, optional):
            Polling interval in seconds. Defaults to 5.

    Returns:
        VirtualMachineForTests:
            Wrapper object representing the restored VM, guaranteed to be in Running state.

    Raises:
        TimeoutError:
            If no VM with the specified prefix appears within the timeout, or if the VM
            fails to stabilize or reach Running state within the allowed time.

    """

    LOGGER.info(f"Waiting for restored VM with prefix {vm_name_prefix}")

    # Step 1: wait until VM appears
    def find_vm():
        try:
            vms = VirtualMachine.get(client=admin_client, namespace=namespace)
        except ResourceNotFoundError:
            return None

        for vm in vms:
            if vm.name.startswith(vm_name_prefix):
                LOGGER.info(f"Found restored VM {vm.name}")
                return vm

        return None

    vm = None
    try:
        for sample in TimeoutSampler(wait_timeout=timeout, sleep=sleep, func=find_vm):
            if sample:
                vm = sample
                break
    except TimeoutExpiredError as error:
        raise TimeoutError(f"VM with prefix {vm_name_prefix} not found in namespace {namespace}") from error

    # Wrap into QE VM object
    vm_wrapper = VirtualMachineForTests(name=vm.name, namespace=namespace, client=admin_client)

    # Step 2: wait until VM becomes stable (no more recreate / 404)
    LOGGER.info(f"Waiting for VM {vm.name} to stabilize")

    def vm_stable():
        try:
            vm_wrapper.instance.get()
            return True
        except ResourceNotFoundError:
            LOGGER.info(f"VM {vm.name} temporarily disappeared, waiting...")
            return False

    for _ in TimeoutSampler(wait_timeout=timeout, sleep=sleep, func=vm_stable):
        pass

    # Step 3: wait until VM Running
    LOGGER.info(f"Waiting for VM {vm.name} to reach Running")

    wait_for_running_vm(vm=vm_wrapper)

    LOGGER.info(f"Restored VM {vm.name} is Running")

    return vm_wrapper
