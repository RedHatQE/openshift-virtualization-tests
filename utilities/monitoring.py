import logging

from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import (
    FIRING_STATE,
    KUBEVIRT_HYPERCONVERGED_OPERATOR_HEALTH_STATUS,
    OPERATOR_HEALTH_IMPACT_VALUES,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
)
from utilities.data_collector import collect_alerts_data

LOGGER = logging.getLogger(__name__)


def wait_for_alert(prometheus, alert):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_5SEC,
        func=prometheus.get_all_alerts_by_alert_name,
        alert_name=alert,
    )
    sample = None
    try:
        for sample in sampler:
            if sample:
                return sample
    except TimeoutExpiredError:
        LOGGER.error(f"Failed to get successful alert {alert}. Current data: {sample}")
        collect_alerts_data()
        raise


def validate_alert_cnv_labels(
    alerts,
    labels,
):
    mismatch_alerts = []
    LOGGER.info(f"Checking alerts: {alerts}")
    for alert in alerts:
        alert_labels = alert["labels"]
        for label in labels:
            LOGGER.info(f"Checking label {label} value is: {alert_labels[label]}")
            alert_label_value = alert_labels[label]
            if alert_label_value != labels[label]:
                LOGGER.error(f"Expected {label} value : {labels[label]}, actual {label} value: {alert_label_value}")
                mismatch_alerts.append(alert)
    assert not mismatch_alerts, f"Following alerts has missing CNV labels or mismatch in alert label: {mismatch_alerts}"


def wait_for_firing_alert_clean_up(prometheus, alert_name, timeout=TIMEOUT_5MIN):
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_5SEC,
        func=prometheus.get_firing_alerts,
        alert_name=alert_name,
    )
    try:
        for sample in samples:
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Alert: {alert_name} did not get clear in {timeout} seconds.")
        raise


def validate_alerts(
    prometheus,
    alert_dict,
    timeout=TIMEOUT_10MIN,
    state=FIRING_STATE,
):
    alert_name = alert_dict.get("alert_name")
    alerts = None
    try:
        alerts = prometheus.wait_for_alert_by_state_sampler(
            alert_name=alert_name,
            timeout=alert_dict.get("timeout", timeout),
            state=alert_dict.get("state", state),
        )
    except TimeoutExpiredError:
        LOGGER.warning(f"Alert {alert_name} not found in firing state. Looking for it in different state.")
        alerts_not_firing = prometheus.get_all_alerts_by_alert_name(alert_name=alert_name)
        LOGGER.info(f"Alert: {alerts_not_firing}")
        if alerts_not_firing:
            alerts = alerts_not_firing
            LOGGER.info(
                f"Alert: {alert_name}, is not fired after {timeout}, but it is found in other state {alerts_not_firing}"
            )
        else:
            collect_alerts_data()
            raise
    try:
        validate_alert_cnv_labels(
            alerts=alerts,
            labels=alert_dict.get("labels"),
        )
        if state == FIRING_STATE:
            wait_for_operator_health_metrics_value(
                prometheus=prometheus,
                health_impact_value=alert_dict["labels"].get("operator_health_impact"),
            )

    except TimeoutExpiredError:
        collect_alerts_data()
        raise


def wait_for_operator_health_metrics_value(
    prometheus,
    health_impact_value,
):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_5SEC,
        func=get_metrics_value,
        prometheus=prometheus,
        metrics_name=KUBEVIRT_HYPERCONVERGED_OPERATOR_HEALTH_STATUS,
    )
    operator_health_metrics_value = OPERATOR_HEALTH_IMPACT_VALUES[health_impact_value]
    LOGGER.info(f"Based on operator label, expected health metrics value: {operator_health_metrics_value}")
    sample = None
    system_metrics_value = None
    try:
        for sample in samples:
            system_metrics_value = get_metrics_value(
                prometheus=prometheus, metrics_name="kubevirt_hco_system_health_status"
            )
            expected_heath_impact = max(system_metrics_value, operator_health_metrics_value)
            LOGGER.info(
                f"System metrics value: {system_metrics_value}, expected health impact: {expected_heath_impact}"
            )
            if str(sample) == str(expected_heath_impact):
                return True
    except TimeoutExpiredError:
        LOGGER.info(f"Operator metrics value: {sample}")
        alerts = get_all_firing_alerts(prometheus=prometheus)
        LOGGER.info(f"All firing alerts:{alerts}")
        alerts_with_higher_health_impact = []
        for health_impact_number in alerts:
            if health_impact_number > operator_health_metrics_value and alerts[health_impact_number]:
                alerts_with_higher_health_impact.extend(alerts[health_impact_number])

        if alerts_with_higher_health_impact:
            LOGGER.warning(
                f"Current system metrics value: {system_metrics_value} and following "
                f"{len(alerts_with_higher_health_impact)} alerts are in firing state"
                f" with higher health impact values: {alerts_with_higher_health_impact}"
            )
            return True
        raise


def get_all_firing_alerts(prometheus):
    alerts = prometheus.alerts()["data"]["alerts"]
    firing_alerts = {}
    for alert in alerts:
        if alert["state"] == "firing":
            health_value = OPERATOR_HEALTH_IMPACT_VALUES[alert["labels"].get("operator_health_impact", "none")]
            if health_value not in firing_alerts:
                firing_alerts[health_value] = []
            firing_alerts[health_value].append(alert["labels"]["alertname"])
    return firing_alerts


def get_metrics_value(prometheus, metrics_name):
    metric_results = prometheus.query(query=metrics_name)["data"]["result"]
    if metric_results:
        metric_values_list = [value for metric_val in metric_results for value in metric_val.get("value")]
        return metric_values_list[1]
    LOGGER.warning(f"For Query {metrics_name}, empty results found.")
    return 0


def wait_for_gauge_metrics_value(prometheus, query, expected_value, timeout=TIMEOUT_5MIN):
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_5SEC,
        func=prometheus.query,
        query=query,
    )
    sample = None

    try:
        for sample in samples:
            if sample:
                result = sample["data"]["result"]
                if result and result[0]["value"] and str(result[0]["value"][1]) == expected_value:
                    return
    except TimeoutExpiredError:
        LOGGER.error(f"Query: {query} did not return expected result {expected_value}, actual result: {sample}")
        raise
