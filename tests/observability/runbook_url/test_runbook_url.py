import logging

import pytest
import requests

from utilities.constants import CNV_PROMETHEUS_RULES, TIMEOUT_10SEC

LOGGER = logging.getLogger(__name__)


def validate_downstream_runbook_url(
    runbook_urls_from_prometheus_rule: dict[str, str],
    subtests: pytest.Subtests,
) -> None:
    """Validate that all runbook URLs exist in the openshift/runbooks repository.

    Args:
        runbook_urls_from_prometheus_rule: Dict items view of (alert_name, runbook_url) pairs.
        subtests: pytest subtests fixture for independent subtest execution.
    """
    expected_prefix = "https://github.com/openshift/runbooks/blob/"
    expected_dir = "alerts/openshift-virtualization-operator/"
    for alert_name, runbook_url in runbook_urls_from_prometheus_rule:
        with subtests.test(msg=alert_name):
            assert runbook_url, f"Alert '{alert_name}' is missing runbook URL, runbook_url is {runbook_url}"
            assert runbook_url.startswith(expected_prefix) and expected_dir in runbook_url, (
                f"Alert '{alert_name}' runbook URL '{runbook_url}' does not match expected format "
                f"(must start with '{expected_prefix}' and contain '{expected_dir}')"
            )
            raw_url = runbook_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            response = requests.head(url=raw_url, timeout=TIMEOUT_10SEC)
            LOGGER.info(f"Runbook URL check for '{alert_name}': {raw_url} returned {response.status_code}")
            assert response.status_code == requests.codes.ok, (
                f"Alert '{alert_name}' runbook URL '{runbook_url}' not found in runbooks repository "
                f"(HTTP {response.status_code})"
            )


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

    @pytest.mark.polarion("CNV-10084")
    def test_runbook_downstream_urls(self, cnv_alerts_runbook_urls_from_prometheus_rule, subtests):
        validate_downstream_runbook_url(
            runbook_urls_from_prometheus_rule=cnv_alerts_runbook_urls_from_prometheus_rule.items(),
            subtests=subtests,
        )
