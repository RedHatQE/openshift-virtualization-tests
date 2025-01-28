import logging

from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError, ResourceNotFoundError
from ocp_resources.namespace import Namespace
from ocp_utilities.monitoring import Prometheus
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.constants import SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED
from utilities.constants import (
    TIMEOUT_2MIN,
    TIMEOUT_4MIN,
    TIMEOUT_15SEC,
)
from utilities.infra import get_pod_by_name_prefix
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


def wait_for_kubemacpool_pods_error_state(dyn_client: DynamicClient, hco_namespace: Namespace) -> None:
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
