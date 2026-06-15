"""
Post-test alerts verification.

Verifies that critical CNV alerts were not triggered during test execution.

Jira: https://redhat.atlassian.net/browse/CNV-80353
"""

import logging

import pytest

LOGGER = logging.getLogger(__name__)

POST_TEST_CRITICAL_ALERTS = [
    "KubeVirtDeprecatedAPIRequested",
    "LowVirtControllersCount",
    "LowVirtAPICount",
    "KubeVirtCRModified",
    "VirtControllerRESTErrorsHigh",
    "VirtHandlerRESTErrorsHigh",
    "HCOOperatorConditionsUnhealthy",
]


@pytest.mark.s390x
@pytest.mark.polarion("CNV-16276")
@pytest.mark.order("last")
def test_no_critical_alerts_after_tests(prometheus):
    """
    Test that critical CNV alerts were not triggered during test execution.

    Preconditions:
        - Prometheus is accessible on the cluster
        - Test execution completed

    Steps:
        1. Query Prometheus for each alert in the critical alerts list
        2. Check that none of the listed alerts are in firing state

    Expected:
        - None of the critical alerts are firing
    """
    LOGGER.info(f"Checking {len(POST_TEST_CRITICAL_ALERTS)} critical alerts were not triggered during test execution")
    fired_alerts = {}
    for alert_name in POST_TEST_CRITICAL_ALERTS:
        alerts_by_name = prometheus.get_all_alerts_by_alert_name(alert_name=alert_name)
        firing_alerts = [alert for alert in alerts_by_name if alert.get("state") == "firing"]
        if firing_alerts:
            fired_alerts[alert_name] = alerts_by_name
    assert not fired_alerts, f"Critical alerts should not be fired after test execution.\n{fired_alerts}"
