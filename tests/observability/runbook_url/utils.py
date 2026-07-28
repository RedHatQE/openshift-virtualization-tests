import logging

import pytest

LOGGER = logging.getLogger(__name__)

RUNBOOK_BLOB_PREFIX = "https://github.com/openshift/runbooks/blob/master/"
RUNBOOK_RAW_PREFIX = "https://raw.githubusercontent.com/openshift/runbooks/master/"


def github_blob_url_to_raw(blob_url: str) -> str:
    """Convert an openshift/runbooks GitHub blob URL to its raw.githubusercontent.com equivalent.

    Args:
        blob_url: A GitHub blob URL (e.g., https://github.com/openshift/runbooks/blob/master/alerts/.../Alert.md).

    Returns:
        The corresponding raw content URL.

    Raises:
        ValueError: If the URL does not match the expected openshift/runbooks blob format.
    """
    if not blob_url.startswith(RUNBOOK_BLOB_PREFIX):
        raise ValueError(f"URL does not match expected prefix '{RUNBOOK_BLOB_PREFIX}': {blob_url}")

    return blob_url.replace(RUNBOOK_BLOB_PREFIX, RUNBOOK_RAW_PREFIX, 1)


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
    expected_prefix = "https://github.com/openshift/runbooks/blob/"
    expected_dir = "alerts/openshift-virtualization-operator/"
    for rule_name, alerts_dict in cnv_prometheus_rule_alerts.items():
        for alert_name, runbook_url in alerts_dict.items():
            with subtests.test(msg=f"{rule_name}/{alert_name}"):
                assert runbook_url, f"Alert '{alert_name}' is missing runbook URL, runbook_url is {runbook_url}"
                assert runbook_url.startswith(expected_prefix) and expected_dir in runbook_url, (
                    f"Alert '{alert_name}' runbook URL '{runbook_url}' does not match expected format "
                    f"(must start with '{expected_prefix}' and contain '{expected_dir}')"
                )
                assert runbook_url in available_runbook_urls, (
                    f"Alert '{alert_name}' runbook URL '{runbook_url}' not found in runbooks repository"
                )
