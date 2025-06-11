import datetime
import logging

from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.namespace import Namespace
from ocp_utilities.monitoring import Prometheus
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.constants import SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED
from utilities.constants import (
    TIMEOUT_4MIN,
    TIMEOUT_15SEC,
)
from utilities.monitoring import get_metrics_value

LOGGER = logging.getLogger(__name__)
ALLOW_ALERTS_ON_HEALTHY_CLUSTER_LIST = [SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED]


def validate_metrics_value(
    prometheus: Prometheus, metric_name: str, expected_value: str, timeout: int = TIMEOUT_4MIN
) -> None:
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_15SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=metric_name,
    )
    sample = None
    comparison_values_log = {}
    try:
        for sample in samples:
            if sample:
                comparison_values_log[datetime.datetime.now()] = (
                    f"metric: {metric_name} value is: {sample}, the expected value is {expected_value}"
                )
                if sample == expected_value:
                    LOGGER.info("Metrics value matches the expected value!")
                    return
    except TimeoutExpiredError:
        LOGGER.error(f"Metrics value: {sample}, expected: {expected_value}, comparison log: {comparison_values_log}")
        raise


def verify_no_listed_alerts_on_cluster(prometheus: Prometheus, alerts_list: list[str]) -> None:
    """
    It gets a list of alerts and verifies that none of them are firing on a cluster.
    """
    fired_alerts = {}
    for alert in alerts_list:
        alerts_by_name = prometheus.get_all_alerts_by_alert_name(alert_name=alert)
        if alerts_by_name and alerts_by_name[0]["state"] == "firing":
            if alert in ALLOW_ALERTS_ON_HEALTHY_CLUSTER_LIST:
                continue
            fired_alerts[alert] = alerts_by_name
    assert not fired_alerts, f"Alerts should not be fired on healthy cluster.\n {fired_alerts}"


def get_olm_namespace() -> Namespace:
    olm_ns = Namespace(name="openshift-operator-lifecycle-manager")
    if olm_ns.exists:
        return olm_ns
    raise ResourceNotFoundError(f"Namespace: {olm_ns.name} not found.")
