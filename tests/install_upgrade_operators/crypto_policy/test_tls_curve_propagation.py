"""
TLS curve (group) propagation tests for CNV endpoints.

Epic: https://redhat.atlassian.net/browse/CNV-82576 # <skip-jira-utils-check>
"""

import logging

import pytest

from tests.install_upgrade_operators.crypto_policy.utils import probe_service_curve_negotiated
from utilities.infra import ExecCommandOnPod

LOGGER = logging.getLogger(__name__)
pytestmark = pytest.mark.post_upgrade


@pytest.mark.usefixtures(
    "custom_curve_profile_applied",
    "verified_node_curve_propagation_support",
    "console_plugin_test_network_policy",
)
def test_custom_profile_curves_propagate_to_cnv_services(
    subtests, curve_propagation_expectations, probe_groups, workers_utility_pods, worker_node1
):
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
    worker_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=worker_node1)
    for service_name, expectation in curve_propagation_expectations.items():
        service = expectation["service"]
        pending_jira = expectation["pending_jira"]
        expected_negotiable = expectation["expected_negotiable"]
        for group in probe_groups:
            with subtests.test(msg=f"{service_name}-{group}"):
                negotiated = probe_service_curve_negotiated(worker_exec=worker_exec, service=service, group=group)
                # Reachability is asserted for every service, including pending ones:
                # None means the probe saw neither a successful handshake nor a rejection.
                assert negotiated is not None, f"Service {service_name} is unreachable for curve {group}"
                if pending_jira:
                    xfail_reason = f"Service {service_name} curve propagation pending {pending_jira}"
                    LOGGER.warning(xfail_reason)
                    pytest.xfail(reason=xfail_reason)
                if group in expected_negotiable:
                    assert negotiated, f"Service {service_name} must negotiate configured curve {group}"
                else:
                    assert not negotiated, f"Service {service_name} must reject curve {group} (omitted or stripped)"
