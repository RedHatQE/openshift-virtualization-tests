import logging

from kubernetes.dynamic.exceptions import NotFoundError
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_2MIN, TIMEOUT_4MIN, TIMEOUT_15SEC
from utilities.infra import get_pod_by_name_prefix
from utilities.monitoring import get_metrics_value

LOGGER = logging.getLogger(__name__)


def validate_metrics_value(prometheus, metric_name, expected_value, timeout=TIMEOUT_4MIN):
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_15SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=metric_name,
    )
    try:
        sample = None
        for sample in samples:
            if sample:
                LOGGER.info(f"metric: {metric_name} value is: {sample}, the expected value is {expected_value}")
                if sample == expected_value:
                    LOGGER.info("Metrics value matches the expected value!")
                    return
    except TimeoutExpiredError:
        LOGGER.info(f"Metrics value: {sample}, expected: {expected_value}")
        raise


def validate_metric_value_within_range(prometheus, metric_name, expected_value, timeout=TIMEOUT_4MIN):
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_15SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=metric_name,
    )
    sample = None
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
