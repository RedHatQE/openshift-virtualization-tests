import logging

import pytest
from ocp_resources.prometheus_rule import PrometheusRule

from tests.utils import validate_runbook_url_exists
from utilities.constants import CNV_PROMETHEUS_RULES

LOGGER = logging.getLogger(__name__)


def get_downstream_runbook_url(alert_name):
    return f"https://github.com/openshift/runbooks/blob/master/alerts/openshift-virtualization-operator/{alert_name}.md"


def get_upstream_runbook_url(alert_name):
    return f"https://github.com/kubevirt/monitoring/blob/main/docs/runbooks/{alert_name}.md"


@pytest.fixture(scope="module")
def cnv_prometheus_rules_names(hco_namespace):
    return [prometheus_rule.name for prometheus_rule in PrometheusRule.get(namespace=hco_namespace.name)]


@pytest.mark.polarion("CNV-10081")
@pytest.mark.s390x
def test_no_new_prometheus_rules(cnv_prometheus_rules_names):
    """
    Since validations for runbook url of all cnv alerts are done via polarion parameterization of prometheusrules,
    this test has been added to catch any new cnv prometheusrules that is not part of cnv_prometheus_rules_matrix
    """
    assert sorted(CNV_PROMETHEUS_RULES) == sorted(cnv_prometheus_rules_names), (
        f"New cnv prometheusrule found: {set(cnv_prometheus_rules_names) - set(CNV_PROMETHEUS_RULES)}"
    )


@pytest.fixture()
def cnv_prometheus_rules_unique_alert_names_runbook(cnv_alerts_from_prometheus_rule):
    alert_runbook_dict = {}
    for alert in cnv_alerts_from_prometheus_rule:
        alert_runbook_dict.setdefault(alert["alert"], set()).add(alert["annotations"]["runbook_url"])
    alerts_with_multiple_runbooks = {
        alert_name: runbook_urls for alert_name, runbook_urls in alert_runbook_dict.items() if len(runbook_urls) > 1
    }
    assert not alerts_with_multiple_runbooks, (
        f"Alerts with multiple different runbook URLs found: {alerts_with_multiple_runbooks}"
    )
    return alert_runbook_dict


@pytest.mark.polarion("CNV-10083")
@pytest.mark.s390x
def test_runbook_upstream_urls(cnv_prometheus_rules_unique_alert_names_runbook):
    url_not_reachable = {}
    for alert_name in cnv_prometheus_rules_unique_alert_names_runbook.keys():
        url_not_reachable[alert_name] = validate_runbook_url_exists(url=get_upstream_runbook_url(alert_name=alert_name))
    not_reachable_url = list(
        filter(
            lambda _alert_name: url_not_reachable[_alert_name] is not None,
            url_not_reachable,
        )
    )
    if not_reachable_url:
        LOGGER.error(f"Upstream runbook url not reachable for following CNV alerts: {not_reachable_url}")
        raise AssertionError("CNV alerts with unreachable runbook urls found.")


@pytest.mark.polarion("CNV-10084")
@pytest.mark.s390x
def test_runbook_downstream_urls(cnv_prometheus_rules_unique_alert_names_runbook):
    error_messages = []
    alerts_without_runbook = {}
    for alert_name, runbook_url in cnv_prometheus_rules_unique_alert_names_runbook.items():
        runbook_url = next(iter(runbook_url))
        expected_url = get_downstream_runbook_url(alert_name=alert_name)
        if not runbook_url or runbook_url != expected_url:
            LOGGER.error(f"For alert: {alert_name}, expected url: {expected_url}, actual url: {runbook_url}")
            alerts_without_runbook[alert_name] = alert_name
        error = validate_runbook_url_exists(url=expected_url)
        if error:
            error_messages.append(error)
    if alerts_without_runbook:
        LOGGER.error(f"Runbook url missing for following CNV alerts: {alerts_without_runbook}")
        raise AssertionError("CNV alerts with missing runbook url found.")

    if error_messages:
        message = f"Downstream runbook url validation failed for the followings: {error_messages}"
        LOGGER.error(message)
        raise AssertionError(message)
