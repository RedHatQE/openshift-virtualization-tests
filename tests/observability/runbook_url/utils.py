import logging
from urllib.parse import urlparse

import pytest

LOGGER = logging.getLogger(__name__)


def github_blob_url_to_raw(blob_url: str) -> str:
    """Convert a GitHub blob URL to its raw.githubusercontent.com equivalent.

    Args:
        blob_url: A GitHub blob URL (e.g., https://github.com/owner/repo/blob/ref/path/file.md).

    Returns:
        The corresponding raw content URL.

    Raises:
        ValueError: If the URL is not a valid GitHub blob URL.
    """
    parsed = urlparse(url=blob_url)
    if parsed.hostname != "github.com":
        raise ValueError(f"Not a github.com URL: {blob_url}")

    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 5 or path_parts[2] != "blob":
        raise ValueError(f"Not a GitHub blob URL: {blob_url}")

    owner, repo = path_parts[0], path_parts[1]
    ref_and_path = "/".join(path_parts[3:])
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref_and_path}"


def validate_downstream_runbook_url(
    cnv_prometheus_rule_alerts: dict[str, dict[str, str]],
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
