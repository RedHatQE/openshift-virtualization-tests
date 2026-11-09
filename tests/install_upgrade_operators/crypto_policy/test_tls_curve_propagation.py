"""
TLS curve (group) propagation tests for CNV endpoints.

Epic: https://redhat.atlassian.net/browse/CNV-74453 # <skip-jira-utils-check>
"""

import pytest

pytestmark = pytest.mark.post_upgrade


def test_custom_profile_curves_propagate_to_cnv_services(subtests, curve_propagation_expectations):
    """
    Test that configured TLS curves propagate from HCO to all CNV services.

    Jira: https://redhat.atlassian.net/browse/CNV-96294  # <skip-jira-utils-check>

    Preconditions:
        - AAQ enabled
        - NetworkPolicy allowing test access to console-plugin pods
        - Worker node OpenSSL supports the probed TLS groups
        - A Custom TLS profile with a curated curve set (including a non-default
          post-quantum hybrid) and one deliberately omitted curve is applied and
          propagated to all managed components
        - All CNV services with a clusterIP discovered
        - Per-service expected negotiation outcome and pending-Jira gate computed

    Steps:
        1. For each CNV service, probe every configured curve and the omitted curve
           individually.

    Expected:
        - Every configured curve is negotiated and the omitted curve is rejected,
          except where the cluster FIPS mode or the component strips non-FIPS curves.
        - Services whose curve propagation is tracked by an open Jira are reported as
          an expected failure (xfail) referencing that Jira, instead of a hard failure.
    """
    for service_name, expectation in curve_propagation_expectations.items():
        pending_jira = expectation["pending_jira"]
        expected_negotiable = expectation["expected_negotiable"]
        for group, negotiated in expectation["group_status"].items():
            with subtests.test(msg=f"{service_name}-{group}"):
                # Reachability is asserted for every service, including pending ones:
                # None means the probe saw neither a successful handshake nor a rejection.
                assert negotiated is not None, f"Service {service_name} is unreachable for curve {group}"
                if pending_jira:
                    pytest.xfail(reason=f"Service {service_name} curve propagation pending {pending_jira}")
                if group in expected_negotiable:
                    assert negotiated, f"Service {service_name} must negotiate configured curve {group}"
                else:
                    assert not negotiated, f"Service {service_name} must reject curve {group} (omitted or stripped)"
