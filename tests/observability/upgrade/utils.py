import logging

from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_5MIN, TIMEOUT_30SEC
from utilities.monitoring import get_metrics_value

LOGGER = logging.getLogger(__name__)


def wait_for_greater_than_zero_metric_value(prometheus, metric_name):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=metric_name,
    )
    sample = None
    try:
        for sample in samples:
            if sample and int(sample) > 0:
                return
    except TimeoutExpiredError:
        LOGGER.info(f"Metric value of: {metric_name} is: {sample}, expected value: non zero")
        raise
