import logging

from ocp_utilities.operators import TIMEOUT_5MIN
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import (
    TIMEOUT_5SEC,
)
from utilities.infra import get_not_running_pods, get_pod_by_name_prefix

LOGGER = logging.getLogger(__name__)


def wait_for_pod_running_by_prefix(
    admin_client,
    namespace_name,
    pod_prefix,
    expected_number_of_pods,
    number_of_consecutive_checks=3,
    timeout=TIMEOUT_5MIN,
):
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_5SEC,
        func=get_pod_by_name_prefix,
        client=admin_client,
        pod_prefix=pod_prefix,
        namespace=namespace_name,
        get_all=True,
    )
    pod_names = None
    not_running_pods = None
    try:
        current_check = 0
        for sample in samples:
            if sample:
                not_running_pods = get_not_running_pods(pods=sample)
                pod_names = [pod.name for pod in sample]
                LOGGER.info(f"All {pod_prefix} pods: {pod_names}, not running: {not_running_pods}")
                if not_running_pods:
                    current_check = 0
                else:
                    if expected_number_of_pods == len(sample):
                        current_check += 1
                    else:
                        current_check = 0
            if current_check >= number_of_consecutive_checks:
                return True
    except TimeoutExpiredError:
        LOGGER.error(
            f"timeout waiting for all {pod_prefix} pods in namespace {namespace_name} to reach "
            f"running state, out of {pod_names}, following pods are in not running state: {not_running_pods}"
        )
        raise
