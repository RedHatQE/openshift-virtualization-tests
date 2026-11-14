"""
TLS curve (group) propagation tests for CNV endpoints.

Epic: https://redhat.atlassian.net/browse/CNV-82576 # <skip-jira-utils-check>
"""

import pytest

from tests.install_upgrade_operators.crypto_policy.utils import (
    assert_curve_reachable_or_xfail_pending,
    probe_service_curve_negotiated,
)

pytestmark = pytest.mark.post_upgrade


@pytest.mark.usefixtures(
    "custom_curve_profile_applied",
    "verified_node_curve_propagation_support",
    "console_plugin_test_network_policy",
)
class TestCustomProfileCurvePropagation:
    """
    Preconditions:
        - AAQ enabled
        - NetworkPolicy allowing test access to console-plugin pods
        - Worker node OpenSSL supports the probed TLS groups
        - A Custom TLS profile with a curated curve set (including a non-default
          post-quantum hybrid) and one deliberately omitted curve is applied and
          propagated to all managed components
        - All CNV services with a clusterIP discovered
        - Per-service expected negotiation outcome and pending-Jira gate computed
    """

    def test_configured_tls_curves_negotiate_on_cnv_services(
        self, subtests, curve_propagation_expectations, worker_exec
    ):
        """
        Test that every curve configured in the Custom TLS profile is negotiated by CNV services.

        Jira: https://redhat.atlassian.net/browse/CNV-96294  # <skip-jira-utils-check>

        Steps:
            1. For each CNV service, probe every curve expected to be negotiable for
               that service (the configured curves, minus any the cluster's FIPS mode
               or the component strips).

        Expected:
            - Every expected-negotiable curve is successfully negotiated.
            - Services whose curve propagation is tracked by an open Jira are reported
              as an expected failure (xfail) referencing that Jira, instead of a hard
              failure.
        """
        for service_name, expectation in curve_propagation_expectations.items():
            service = expectation["service"]
            pending_jira = expectation["pending_jira"]
            for group in expectation["expected_negotiable"]:
                with subtests.test(msg=f"{service_name}-{group}"):
                    negotiated = probe_service_curve_negotiated(worker_exec=worker_exec, service=service, group=group)
                    assert_curve_reachable_or_xfail_pending(
                        negotiated=negotiated, service_name=service_name, group=group, pending_jira=pending_jira
                    )
                    assert negotiated, f"Service {service_name} must negotiate configured curve {group}"

    def test_omitted_tls_curve_is_rejected_on_cnv_services(
        self, subtests, curve_propagation_expectations, probe_groups, worker_exec
    ):
        """
        [NEGATIVE] Test that curves not expected to be negotiable are rejected by CNV services.

        Jira: https://redhat.atlassian.net/browse/CNV-96294  # <skip-jira-utils-check>

        Steps:
            1. For each CNV service, probe every curve not expected to be negotiable
               for that service (the curve deliberately omitted from the Custom
               profile, plus any configured curve the cluster's FIPS mode or the
               component strips).

        Expected:
            - Every such curve is rejected.
            - Services whose curve propagation is tracked by an open Jira are reported
              as an expected failure (xfail) referencing that Jira, instead of a hard
              failure.
        """
        for service_name, expectation in curve_propagation_expectations.items():
            service = expectation["service"]
            pending_jira = expectation["pending_jira"]
            expected_negotiable = expectation["expected_negotiable"]
            for group in probe_groups:
                if group in expected_negotiable:
                    continue
                with subtests.test(msg=f"{service_name}-{group}"):
                    negotiated = probe_service_curve_negotiated(worker_exec=worker_exec, service=service, group=group)
                    assert_curve_reachable_or_xfail_pending(
                        negotiated=negotiated, service_name=service_name, group=group, pending_jira=pending_jira
                    )
                    assert not negotiated, f"Service {service_name} must reject curve {group} (omitted or stripped)"
