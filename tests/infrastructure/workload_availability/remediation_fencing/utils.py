"""
Node Health Check common use cases
"""

import base64
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.bare_metal_host import BareMetalHost
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
from utilities.exceptions import ResourceMissingFieldError, ResourceValueError
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.virt import wait_for_node_schedulable_status, wait_for_vmi_relocation_and_running

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

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


def bmc_details_from_bare_metal_hosts(
    admin_client: DynamicClient, worker_node_names: list[str]
) -> dict[str, dict[str, str]]:
    """Read BMC address and credentials for worker BareMetalHosts.

    The installer blanks BMC username and password in the cluster-config-v1
    install-config, so credentials are read from BareMetalHost secrets.
    Each name in ``worker_node_names`` must match a BareMetalHost name in
    ``openshift-machine-api``.

    Args:
        admin_client (DynamicClient): Cluster admin client.
        worker_node_names (list[str]): Worker node names whose BMC secrets to read.

    Returns:
        dict[str, dict[str, str]]: Mapping of worker BareMetalHost name to
            ``address``, ``username``, and ``password``.

    Raises:
        ResourceNotFoundError: If no BareMetalHost objects are found, a worker
            has no matching BareMetalHost, or a worker BMC secret does not exist.
        ResourceMissingFieldError: If a worker BareMetalHost has no spec.bmc, or its
            BMC secret has no username or password.
    """
    bmh_namespace = NamespacesNames.MACHINE_API_NAMESPACE
    bare_metal_hosts = {
        bare_metal_host.name: bare_metal_host
        for bare_metal_host in BareMetalHost.get(client=admin_client, namespace=bmh_namespace)
    }
    if not bare_metal_hosts:
        raise ResourceNotFoundError(f"No BareMetalHost objects found in namespace {bmh_namespace}")

    workers_without_bmh = [worker_name for worker_name in worker_node_names if worker_name not in bare_metal_hosts]
    if workers_without_bmh:
        raise ResourceNotFoundError(f"No BareMetalHost named {workers_without_bmh} in {bmh_namespace}")

    bmc_details: dict[str, dict[str, str]] = {}
    for worker_name in worker_node_names:
        bmc_config = bare_metal_hosts[worker_name].instance.spec.bmc
        if bmc_config is None:
            raise ResourceMissingFieldError(f"BareMetalHost {worker_name} has no spec.bmc")
        credentials_name = bmc_config.credentialsName
        bmc_secret = Secret(
            name=credentials_name,
            namespace=bmh_namespace,
            client=admin_client,
            ensure_exists=True,
        )
        secret_data = bmc_secret.instance.data
        if not secret_data or not secret_data.username or not secret_data.password:
            raise ResourceMissingFieldError(
                f"BMC secret {credentials_name} for BareMetalHost {worker_name} is missing username or password"
            )
        bmc_details[worker_name] = {
            "address": bmc_config.address,
            "username": base64.b64decode(s=secret_data.username).decode(encoding="utf-8"),
            "password": base64.b64decode(s=secret_data.password).decode(encoding="utf-8"),
        }

    LOGGER.info(f"Read BMC details for worker hosts: {list(bmc_details)}")
    return bmc_details


def fence_agent_node_parameters(bmc_nodes_ipmi_data: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Convert worker BMC host data into FenceAgentsRemediationTemplate nodeParameters.

    Args:
        bmc_nodes_ipmi_data (dict[str, dict[str, str]]): Mapping of worker
            BareMetalHost name to BMC address, username, and password.

    Returns:
        dict[str, dict[str, str]]: FAR nodeParameters with ``--ip``, ``--ipport``,
            ``--username``, and ``--password`` maps keyed by worker BareMetalHost name.

    Raises:
        ResourceValueError: If a worker BMC address is not ``ipmi://<host>[:port]``.
    """
    node_parameters: dict[str, dict[str, str]] = {"--ip": {}, "--ipport": {}, "--username": {}, "--password": {}}
    for worker_name, params in bmc_nodes_ipmi_data.items():
        bmc_url = urlparse(url=params["address"])
        if bmc_url.scheme != "ipmi" or not bmc_url.hostname:
            raise ResourceValueError(
                f"BMH {worker_name}: fence_ipmilan needs an ipmi://<host>[:port] BMC address, got {params['address']}"
            )
        node_parameters["--ip"][worker_name] = bmc_url.hostname
        node_parameters["--ipport"][worker_name] = str(bmc_url.port or IPMI_DEFAULT_PORT)
        node_parameters["--username"][worker_name] = params["username"]
        node_parameters["--password"][worker_name] = params["password"]
    return node_parameters
