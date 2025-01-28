import logging

from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.namespace import Namespace

from tests.observability.alerts.constants import SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED

KUBEVIRT_HYPERCONVERGED_OPERATOR_HEALTH_STATUS = "kubevirt_hyperconverged_operator_health_status"
ALLOW_ALERTS_ON_HEALTHY_CLUSTER_LIST = [SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED]
CONTAINERIZED_DATA_IMPORTER = "containerized-data-importer"
LOGGER = logging.getLogger(__name__)


def verify_no_listed_alerts_on_cluster(prometheus, alerts_list):
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


def get_olm_namespace():
    olm_ns = Namespace(name="openshift-operator-lifecycle-manager")
    if olm_ns.exists:
        return olm_ns
    raise ResourceNotFoundError(f"Namespace: {olm_ns.name} not found.")
