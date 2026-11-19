"""
Node Health Check common use cases
"""

import base64
import logging
from urllib.parse import urlparse

from ocp_resources.secret import Secret
from timeout_sampler import TimeoutExpiredError, TimeoutSampler
from websocket import WebSocketConnectionClosedException

from tests.infrastructure.workload_availability.remediation_fencing.constants import (
    IPMI_DEFAULT_PORT,
    NODE_ACTIONS_DICT,
)
from utilities.constants.namespaces import NamespacesNames
from utilities.constants.timeouts import (
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
    TIMEOUT_6MIN,
    TIMEOUT_9MIN,
)
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.virt import wait_for_node_schedulable_status, wait_for_vmi_relocation_and_running

LOGGER = logging.getLogger(__name__)


def perform_node_operation(utility_pods, node, action):
    LOGGER.info(f"Perform {action}: {node.name}")
    try:
        ExecCommandOnPod(utility_pods=utility_pods, node=node).exec(command=NODE_ACTIONS_DICT[action], ignore_rc=True)
    except WebSocketConnectionClosedException:
        LOGGER.warning(f"Socket exception: Due to {action}")
    finally:
        wait_for_node_status(node=node, status=False)


def wait_node_restored(node, timeout=TIMEOUT_6MIN):
    LOGGER.info(f"Waiting node {node.name} to be added to cluster and Ready")
    node.wait_for_condition(
        condition=node.Status.READY,
        status=node.Condition.Status.TRUE,
        timeout=timeout,
    )


def wait_for_nodehealthcheck_enabled_phase(nodehealthcheck_object):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: nodehealthcheck_object.exists,
        ):
            if sample and sample.status and sample.status.phase == "Enabled":
                break
    except TimeoutExpiredError:
        LOGGER.error(
            f"Timeout happens while creating node-health-check resource: {nodehealthcheck_object.name}. "
            f"Current status: {nodehealthcheck_object.instance.status}"
        )
        raise


def verify_vm_and_node_recovery_after_node_failure(
    node, vm, timeout_node_restored=TIMEOUT_9MIN, timeout_schedulable=TIMEOUT_2MIN
):
    wait_for_vmi_relocation_and_running(initial_node=node, vm=vm)
    wait_node_restored(node=node, timeout=timeout_node_restored)
    wait_for_node_schedulable_status(node=node, status=True, timeout=timeout_schedulable)


def bmc_details_from_bare_metal_hosts(admin_client):
    """Read BMC address and credentials from BareMetalHost objects and secrets.

    The installer blanks BMC username and password in the cluster-config-v1
    install-config, so credentials are read from BareMetalHost secrets.

    Args:
        admin_client (DynamicClient): Cluster admin client.

    Returns:
        dict: Mapping of BareMetalHost name to a dict with ``address``,
            ``username``, and ``password``.

    Raises:
        ValueError: If no BareMetalHost objects are found, or decoded
            username/password is empty.
        KeyError: If the BMC secret is missing username or password keys.
    """
    bmh_namespace = NamespacesNames.MACHINE_API_NAMESPACE
    bmh_api = admin_client.resources.get(api_version="metal3.io/v1alpha1", kind="BareMetalHost")
    bmh_list = bmh_api.get(namespace=bmh_namespace).items
    if not bmh_list:
        raise ValueError(f"No BareMetalHost objects found in namespace {bmh_namespace}")

    bmc_details = {}
    for bmh in bmh_list:
        bmh_name = bmh.metadata.name
        bmc_config = bmh.spec.bmc
        credentials_name = bmc_config.credentialsName
        secret_data = Secret(name=credentials_name, namespace=bmh_namespace, client=admin_client).instance.data
        username = base64.b64decode(secret_data["username"]).decode()
        password = base64.b64decode(secret_data["password"]).decode()
        if not username or not password:
            raise ValueError(f"Missing username/password in secret {credentials_name} for BMH {bmh_name}")

        bmc_details[bmh_name] = {
            "address": bmc_config.address,
            "username": username,
            "password": password,
        }

    LOGGER.info(f"Extracted BMC credentials for hosts: {list(bmc_details)}")
    return bmc_details


def fence_agent_node_parameters(bmc_nodes_ipmi_data, worker_node_names):
    """Convert worker BMC host data into FenceAgentsRemediationTemplate nodeParameters.

    BareMetalHosts are included when their name matches a worker node. Nodes
    that are both control-plane and worker (compact/SNO) are included because
    they have the worker label. Control-plane-only BareMetalHosts are skipped.

    Args:
        bmc_nodes_ipmi_data (dict): Mapping of BareMetalHost name to BMC
            address, username, and password.
        worker_node_names (list[str]): Worker node names that FAR must be
            able to fence.

    Returns:
        dict: FAR nodeParameters with ``--ip``, ``--ipport``, ``--username``,
            and ``--password`` maps keyed by worker BareMetalHost name.

    Raises:
        ValueError: If a worker BMC address is not ``ipmi://<host>[:port]``,
            or a worker node has no matching BareMetalHost.
    """
    workers_without_bmh = [worker_name for worker_name in worker_node_names if worker_name not in bmc_nodes_ipmi_data]
    if workers_without_bmh:
        raise ValueError(f"No BareMetalHost named after worker nodes: {workers_without_bmh}")

    node_parameters = {"--ip": {}, "--ipport": {}, "--username": {}, "--password": {}}
    for worker_name in worker_node_names:
        params = bmc_nodes_ipmi_data[worker_name]
        bmc_url = urlparse(url=params["address"])
        if bmc_url.scheme != "ipmi" or not bmc_url.hostname:
            raise ValueError(
                f"BMH {worker_name}: fence_ipmilan needs an ipmi://<host>[:port] BMC address, got {params['address']}"
            )
        node_parameters["--ip"][worker_name] = bmc_url.hostname
        node_parameters["--ipport"][worker_name] = str(bmc_url.port or IPMI_DEFAULT_PORT)
        node_parameters["--username"][worker_name] = params["username"]
        node_parameters["--password"][worker_name] = params["password"]
    return node_parameters
