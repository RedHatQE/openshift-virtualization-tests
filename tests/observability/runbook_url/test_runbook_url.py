import http
import logging

import pytest
import requests

from utilities.constants import CNV_PROMETHEUS_RULES

LOGGER = logging.getLogger(__name__)


def validate_downstream_runbook_url(runbook_urls_from_prometheus_rule: dict[str, str]) -> None:
    error_messages = {}
    alerts_without_runbook = []

    for alert_name, runbook_url in runbook_urls_from_prometheus_rule:
        if not runbook_url:
            LOGGER.error(f"For alert: {alert_name} Url not found")
            alerts_without_runbook.append(alert_name)
            continue
        if requests.get(runbook_url, allow_redirects=False).status_code != http.HTTPStatus.OK:
            LOGGER.error(f"Alert {alert_name} url {runbook_url} is not valid")
            error_messages[alert_name] = runbook_url
    assert not (alerts_without_runbook or error_messages), (
        f"CNV alerts with missing runbook url: {alerts_without_runbook}, "
        f"D/S runbook url validation failed for the followings alerts: {error_messages}"
    )


class TestRunbookUrlsAndPrometheusRules:
    @pytest.mark.polarion("CNV-10081")
    def test_no_new_prometheus_rules(self, cnv_prometheus_rules_names):
        """
        Since validations for runbook url of all cnv alerts are done via polarion parameterization of prometheusrules,
        this test has been added to catch any new cnv prometheusrules that is not part of cnv_prometheus_rules_matrix
        """
        assert sorted(CNV_PROMETHEUS_RULES) == sorted(cnv_prometheus_rules_names), (
            f"New cnv prometheusrule found: {set(cnv_prometheus_rules_names) - set(CNV_PROMETHEUS_RULES)}"
        )

    @pytest.mark.polarion("CNV-10084")
    def test_runbook_downstream_urls(self, cnv_alerts_runbook_urls_from_prometheus_rule):
        validate_downstream_runbook_url(
            runbook_urls_from_prometheus_rule=cnv_alerts_runbook_urls_from_prometheus_rule.items()
        )
