import logging

import pytest
import requests
from timeout_sampler import retry

from utilities.constants import CNV_PROMETHEUS_RULES, TIMEOUT_10SEC, TIMEOUT_30SEC

LOGGER = logging.getLogger(__name__)
RUNBOOKS_API_URL = "https://api.github.com/repos/openshift/runbooks/contents/alerts/openshift-virtualization-operator"


@retry(wait_timeout=TIMEOUT_30SEC, sleep=TIMEOUT_10SEC, exceptions_dict={AssertionError: []})
def fetch_runbook_urls_from_github() -> set[str]:
    """Fetch available runbook URLs from the openshift/runbooks GitHub repository.

    Returns:
        Set of runbook HTML URLs available in the repository.
    """
    response = requests.get(url=RUNBOOKS_API_URL, timeout=TIMEOUT_10SEC)
    assert response.status_code == requests.codes.ok, (
        f"Failed to fetch runbooks directory listing from '{RUNBOOKS_API_URL}': status {response.status_code}"
    )
    return {entry["html_url"] for entry in response.json()}


def validate_downstream_runbook_url(
    runbook_urls_from_prometheus_rule: dict[str, str], subtests: pytest.Subtests
) -> None:
    """
    Validate that all runbook URLs exist in the openshift/runbooks repository.

    Fetches the directory listing once from GitHub API and checks each alert's
    runbook URL against the available runbook files.

    Args:
        runbook_urls_from_prometheus_rule: Iterable of (alert_name, runbook_url) tuples
        subtests: pytest subtests fixture for independent subtest execution
    """
    available_runbook_urls = fetch_runbook_urls_from_github()
    for alert_name, runbook_url in runbook_urls_from_prometheus_rule:
        with subtests.test(msg=alert_name):
            assert runbook_url, f"Alert '{alert_name}' is missing runbook URL, runbook_url is {runbook_url}"
            assert runbook_url in available_runbook_urls, (
                f"Alert '{alert_name}' runbook URL '{runbook_url}' not found in runbooks repository"
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
