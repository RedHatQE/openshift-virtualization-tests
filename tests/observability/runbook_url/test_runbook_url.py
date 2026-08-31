import pytest


def validate_downstream_runbook_url(
    runbook_urls_from_prometheus_rule: dict[str, str],
    available_runbook_urls: set[str],
    subtests: pytest.Subtests,
) -> None:
    """Validate that all runbook URLs exist in the openshift/runbooks repository.

    Args:
        runbook_urls_from_prometheus_rule: Dict items view of (alert_name, runbook_url) pairs.
        available_runbook_urls: Set of runbook HTML URLs available in the repository.
        subtests: pytest subtests fixture for independent subtest execution.
    """
    for alert_name, runbook_url in runbook_urls_from_prometheus_rule:
        with subtests.test(msg=alert_name):
            assert runbook_url, f"Alert '{alert_name}' is missing runbook URL, runbook_url is {runbook_url}"
            assert runbook_url in available_runbook_urls, (
                f"Alert '{alert_name}' runbook URL '{runbook_url}' not found in runbooks repository"
            )


class TestRunbookUrlsAndPrometheusRules:
    @pytest.mark.polarion("CNV-10084")
    def test_runbook_downstream_urls(
        self, available_runbook_urls, cnv_alerts_runbook_urls_from_prometheus_rule, subtests
    ):
        validate_downstream_runbook_url(
            runbook_urls_from_prometheus_rule=cnv_alerts_runbook_urls_from_prometheus_rule.items(),
            subtests=subtests,
            available_runbook_urls=available_runbook_urls,
        )
