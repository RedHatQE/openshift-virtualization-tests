"""
Post-test alerts verification.

Verifies that KubeVirtDeprecatedAPIRequested alert was not triggered during test execution.

Jira: https://redhat.atlassian.net/browse/CNV-80353
"""

import logging
from datetime import UTC, datetime

import pytest

from utilities.constants.monitoring import FIRING_STATE

LOGGER = logging.getLogger(__name__)

DEPRECATED_API_ALERT = "KubeVirtDeprecatedAPIRequested"


@pytest.mark.s390x
@pytest.mark.polarion("CNV-16276")
@pytest.mark.order("last")
def test_no_deprecated_api_alert_after_tests(prometheus, session_start_time):
    """
    Test that KubeVirtDeprecatedAPIRequested alert was not triggered during test execution.

    Preconditions:
        - Prometheus is accessible on the cluster
        - Test execution completed

    Steps:
        1. Query Prometheus for KubeVirtDeprecatedAPIRequested alert that fired during test execution
        2. Check that the alert was not triggered

    Expected:
        - KubeVirtDeprecatedAPIRequested alert did not fire during test execution
    """
    elapsed_seconds = max(int((datetime.now(UTC).replace(tzinfo=None) - session_start_time).total_seconds()), 1)
    LOGGER.info(
        f"Checking {DEPRECATED_API_ALERT} alert was not triggered during test execution (last {elapsed_seconds}s)"
    )
    query = f'ALERTS{{alertname="{DEPRECATED_API_ALERT}", alertstate="{FIRING_STATE}"}}[{elapsed_seconds}s]'
    results = prometheus.query_sampler(query=query)
    assert not results, f"{DEPRECATED_API_ALERT} alert should not fire during test execution (last {elapsed_seconds}s)"
