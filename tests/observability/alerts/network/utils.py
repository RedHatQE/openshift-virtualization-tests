import logging

from kubernetes.dynamic.exceptions import NotFoundError
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import (
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
)
from utilities.infra import get_pod_by_name_prefix

KUBEMACPOOL_DOWN = "KubemacpoolDown"
CNAO_NOT_READY = "NetworkAddonsConfigNotReady"
CNAO_DOWN = "CnaoDown"
LOGGER = logging.getLogger(__name__)


def wait_for_kubemacpool_pods_error_state(dyn_client, hco_namespace):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=1,
        func=get_pod_by_name_prefix,
        dyn_client=dyn_client,
        pod_prefix="kubemacpool",
        namespace=hco_namespace.name,
        exceptions_dict={NotFoundError: []},
        get_all=True,
    )
    for sample in samples:
        if any([pod.exists and pod.status == pod.Status.PENDING for pod in sample]):
            return


def wait_for_cnao_pod_running(admin_client, hco_namespace):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=get_pod_by_name_prefix,
        dyn_client=admin_client,
        pod_prefix=CLUSTER_NETWORK_ADDONS_OPERATOR,
        namespace=hco_namespace,
    )
    sample = None
    try:
        for sample in samples:
            if sample.exists and sample.status == sample.Status.RUNNING:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"{sample.name} status is {sample.status}. Expected status is: {sample.Status.RUNNING}")
        raise
