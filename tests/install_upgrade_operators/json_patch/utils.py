import logging

from ocp_resources.resource import Resource
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.json_patch.constants import DISABLE_TLS, PATH_CDI
from utilities.constants import TIMEOUT_5MIN, TIMEOUT_30SEC
from utilities.hco import HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT

LOGGER = logging.getLogger(__name__)


def get_annotation_name_for_component(component_name):
    return (
        f"{HCO_JSONPATCH_ANNOTATION_COMPONENT_DICT[component_name]['api_group_prefix']}."
        f"{Resource.ApiGroup.KUBEVIRT_IO}/jsonpatch"
    )


def wait_for_alert(prometheus, alert_name, component_name):
    annotation_name = get_annotation_name_for_component(component_name=component_name)
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=prometheus.get_firing_alerts,
        alert_name=alert_name,
    )
    sample = None
    try:
        for sample in samples:
            if sample and sample[0]["labels"]["annotation_name"] == annotation_name:
                LOGGER.info(f"Found alert: {sample} in firing state.")
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Alert: {alert_name} did not get created for {annotation_name} in {TIMEOUT_5MIN} seconds."
            f"Current firing alerts are:\n {sample}"
        )


def wait_for_firing_alert_clean_up(prometheus, alert_name):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=prometheus.get_firing_alerts,
        alert_name=alert_name,
    )
    try:
        for sample in samples:
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Alert: {alert_name} did not get clear in {TIMEOUT_5MIN} seconds.")


def get_metrics_value_with_annotation(prometheus, query_string, component_name):
    annotation_name = get_annotation_name_for_component(component_name=component_name)
    query = f'{query_string}{{annotation_name="{annotation_name}"}}'
    metric_results = prometheus.query(query=query)["data"]["result"]
    return int(metric_results[0]["value"][1]) if metric_results else 0


def filter_metric_by_component(metrics, metric_name, component_name):
    annotation_name = get_annotation_name_for_component(component_name=component_name)
    for metric in metrics:
        if metric["metric"]["annotation_name"] == annotation_name and metric["metric"]["__name__"] == metric_name:
            return int(metric["value"][1])


def wait_for_metrics_value_update(prometheus, component_name, query_string, previous_value):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=get_metrics_value_with_annotation,
        prometheus=prometheus,
        component_name=component_name,
        query_string=query_string,
    )
    try:
        for sample in samples:
            if sample == previous_value + 1:
                return sample
    except TimeoutExpiredError:
        LOGGER.error(f"Query string: {query_string} for component: {component_name}, previous value: {previous_value}.")
        raise


def validate_kubevirt_json_patch(kubevirt_resource):
    migration_current_value = kubevirt_resource.instance.spec.configuration.migrations
    assert migration_current_value.get(DISABLE_TLS), (
        f"Unable to json patch kubevirt to set {DISABLE_TLS}. Current Value: {migration_current_value}."
    )


def validate_cdi_json_patch(cdi_resource, before_value):
    cdi_current_feature_gates = cdi_resource.instance.spec.config.get("featureGates", [])
    assert len(before_value) - len(cdi_current_feature_gates) == 1, (
        f"Json patch to remove {PATH_CDI} from CDI was unsuccessful. Current value: {cdi_current_feature_gates}"
    )
