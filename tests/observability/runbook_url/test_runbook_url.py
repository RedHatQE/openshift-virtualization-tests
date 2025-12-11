import logging

import pytest

from tests.utils import validate_runbook_url_exists
from utilities.constants import CNV_PROMETHEUS_RULES, QUARANTINED

LOGGER = logging.getLogger(__name__)


class TestRunbookUrlsAndPrometheusRules:
    @pytest.mark.polarion("CNV-10081")
    def test_no_new_prometheus_rules(self, cnv_prometheus_rules_names, hpp_cr_installed):
        """
        Since validations for runbook url of all cnv alerts are done via polarion parameterization of prometheusrules,
        this test has been added to catch any new cnv prometheusrules that is not part of cnv_prometheus_rules_matrix
        """
        expected_prometheus_rules_names = CNV_PROMETHEUS_RULES.copy()
        if not hpp_cr_installed:
            LOGGER.warning("HPP CR is not installed, removing prometheus-hpp-rules from the list of prometheus rules")
            expected_prometheus_rules_names.remove("prometheus-hpp-rules")
        assert sorted(cnv_prometheus_rules_names) == sorted(expected_prometheus_rules_names), (
            f"New cnv prometheusrule found: {set(cnv_prometheus_rules_names) - set(expected_prometheus_rules_names)}"
        )

    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: New alerts runbooks added to upstream and not merged yet for downstream, CNV-67890",
        run=False,
    )
    @pytest.mark.polarion("CNV-10084")
    def test_runbook_downstream_urls(self, cnv_alerts_runbook_urls_from_prometheus_rule):
        error_messages = {}
        alerts_without_runbook = []

        for alert_name, runbook_url in cnv_alerts_runbook_urls_from_prometheus_rule.items():
            if not runbook_url:
                LOGGER.error(f"For alert: {alert_name} Url not found")
                alerts_without_runbook.append(alert_name)
            error = validate_runbook_url_exists(url=runbook_url)
            if error:
                LOGGER.error(f"Alert {alert_name} url {runbook_url} is not valid")
                error_messages[alert_name] = runbook_url
        if alerts_without_runbook:
            LOGGER.error(f"Runbook url missing for following CNV alerts: {alerts_without_runbook}")
            raise AssertionError("CNV alerts with missing runbook url found.")

        if error_messages:
            message = f"Downstream runbook url validation failed for the followings: {error_messages}"
            LOGGER.error(message)
            raise AssertionError(message)
