"""
Node Health Check common use cases
"""

import logging

from timeout_sampler import TimeoutExpiredError, TimeoutSampler
from websocket import WebSocketConnectionClosedException

from tests.infrastructure.workload_availability.remediation_fencing.constants import (
    NODE_ACTIONS_DICT,
)
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_2MIN, TIMEOUT_5SEC, TIMEOUT_6MIN, TIMEOUT_9MIN
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
