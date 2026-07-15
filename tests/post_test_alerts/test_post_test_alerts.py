"""
Post-test alerts verification.

Verifies that critical CNV alerts were not triggered during test execution.

Jira: https://redhat.atlassian.net/browse/CNV-80353
"""

import datetime
import logging

import pytest

LOGGER = logging.getLogger(__name__)

DEPRECATED_API_ALERT = "KubeVirtDeprecatedAPIRequested"


@pytest.mark.s390x
@pytest.mark.polarion("CNV-16276")
@pytest.mark.order("last")
def test_no_critical_alerts_after_tests(prometheus, request):
    """
    Test that critical CNV alerts were not triggered during test execution.

    Preconditions:
        - Prometheus is accessible on the cluster
        - Test execution completed

    Steps:
        1. Query Prometheus for alerts that fired at any point during test execution
        2. Check that none of the critical alerts were triggered

    Expected:
        - None of the critical alerts fired during test execution
    """
    start_time = request.config._test_execution_start_time
    duration_seconds = max(int((datetime.datetime.now(tz=datetime.UTC) - start_time).total_seconds()), 1)
    LOGGER.info(
        f"Checking {DEPRECATED_API_ALERT} alert was not triggered during test execution (last {duration_seconds}s)"
    )
    query = f'ALERTS{{alertname="{DEPRECATED_API_ALERT}", alertstate="firing"}}[{duration_seconds}s]'
    results = prometheus.query_sampler(query=query)
    assert not results, f"{DEPRECATED_API_ALERT} alert fired during test execution.\n{results}"
