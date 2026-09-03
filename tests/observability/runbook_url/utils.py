import pytest

from utilities.jira import is_jira_open


def github_blob_url_to_raw(blob_url: str) -> str:
    """Convert an openshift/runbooks GitHub blob URL to its raw.githubusercontent.com equivalent.

    Args:
        blob_url: A GitHub blob URL (e.g., https://github.com/openshift/runbooks/blob/master/alerts/.../Alert.md).

    Returns:
        The corresponding raw content URL.
    """
    return blob_url.replace(
        "https://github.com/openshift/runbooks/blob/master/",
        "https://raw.githubusercontent.com/openshift/runbooks/master/",
        1,
    )


def validate_downstream_runbook_url(
    cnv_prometheus_rule_alerts: dict[str, dict[str, str | None]],
    available_runbook_urls: set[str],
    subtests: pytest.Subtests,
) -> None:
    """Validate that all runbook URLs exist in the openshift/runbooks repository.

    Args:
        cnv_prometheus_rule_alerts: Mapping of rule name to {alert_name: runbook_url}.
        available_runbook_urls: Set of runbook URLs available in the repository.
        subtests: pytest subtests fixture for independent subtest execution.
    """
    for rule_name, alerts_dict in cnv_prometheus_rule_alerts.items():
        for alert_name, runbook_url in alerts_dict.items():
            with subtests.test(msg=f"{rule_name}/{alert_name}"):
                assert runbook_url, f"Alert '{alert_name}' is missing runbook URL, runbook_url is {runbook_url}"
                if "kubevirt/virt-platform-autopilot" in runbook_url and is_jira_open(jira_id="CNV-96023"):
                    pytest.xfail(
                        reason="CNV-96023: runbook not located in correct repo"
                        " (kubevirt/virt-platform-autopilot instead of openshift/runbooks)"
                    )
                assert runbook_url in available_runbook_urls, (
                    f"Alert '{alert_name}' runbook URL '{runbook_url}' not found in runbooks repository"
                )
