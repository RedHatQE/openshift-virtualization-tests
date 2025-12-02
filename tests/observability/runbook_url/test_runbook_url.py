import http
import logging

import pytest
import requests

from utilities.constants import CNV_PROMETHEUS_RULES, TIMEOUT_10SEC

LOGGER = logging.getLogger(__name__)


def validate_downstream_runbook_url(
    runbook_urls_from_prometheus_rule: dict[str, str], subtests: pytest.Subtests
) -> None:
    """
    Validate that all runbook URLs are accessible.

    Args:
        runbook_urls_from_prometheus_rule: Iterable of (alert_name, runbook_url) tuples
        subtests: pytest subtests fixture for independent subtest execution
    """
    for alert_name, runbook_url in runbook_urls_from_prometheus_rule:
        with subtests.test(msg=alert_name):
            assert runbook_url, f"Alert '{alert_name}' is missing runbook URL"

            try:
                response = requests.get(runbook_url, allow_redirects=False, timeout=TIMEOUT_10SEC)
                assert response.status_code == http.HTTPStatus.OK, (
                    f"Alert '{alert_name}' runbook URL '{runbook_url}' returned status {response.status_code}"
                )
            except requests.RequestException as e:
                pytest.fail(f"Alert '{alert_name}' runbook URL '{runbook_url}' failed: {e}")


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
    def test_runbook_downstream_urls(self, cnv_alerts_runbook_urls_from_prometheus_rule, subtests):
        validate_downstream_runbook_url(
            runbook_urls_from_prometheus_rule=cnv_alerts_runbook_urls_from_prometheus_rule.items(),
            subtests=subtests,
        )
