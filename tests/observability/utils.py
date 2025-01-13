import logging

from ocp_resources.cluster_role_binding import ClusterRoleBinding
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_4MIN, TIMEOUT_15SEC
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


def get_kubevirt_operator_role_binding_resource(admin_client):
    for crb in list(ClusterRoleBinding.get(dyn_client=admin_client)):
        subjects = crb.instance.subjects
        if subjects and subjects[0].name == "kubevirt-operator":
            return crb
