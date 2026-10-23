"""
TLS curve (group) propagation tests for CNV endpoints.

Epic: https://redhat.atlassian.net/browse/CNV-74453 # <skip-jira-utils-check>
"""

import logging

import pytest

from tests.install_upgrade_operators.crypto_policy.constants import (
    CONSOLE_PLUGIN_SERVICE_NAME,
    CURVE_PROPAGATION_PENDING,
    NON_FIPS_GROUPS,
    TLS_PROPAGATION_CUSTOM_GROUPS,
)
from utilities.jira import is_jira_open

LOGGER = logging.getLogger(__name__)
pytestmark = pytest.mark.post_upgrade


def test_custom_profile_curves_propagate_to_cnv_services(
    subtests, curve_status_by_service, fips_enabled_cluster, services_tls_runtime
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

    Steps:
        1. For each CNV service, probe every configured curve and the omitted curve
           individually.

    Expected:
        - Every configured curve is negotiated and the omitted curve is rejected,
          except where the cluster FIPS mode or the component strips non-FIPS curves.
    """
    for service_name, group_status in curve_status_by_service.items():
        pending_jira = CURVE_PROPAGATION_PENDING.get(service_name)
        pending = bool(pending_jira) and is_jira_open(pending_jira)
        if pending:
            LOGGER.warning(
                f"Service {service_name} curve propagation pending {pending_jira}; checking reachability only"
            )

        expected_negotiable = set(TLS_PROPAGATION_CUSTOM_GROUPS)
        # Curve25519-based groups are not FIPS-approved: Go services drop them under FIPS,
        # and the console-plugin handler strips them unconditionally (GetFIPSCompliantGroups).
        if fips_enabled_cluster:
            assert service_name in services_tls_runtime, f"TLS runtime not detected for service {service_name}"
            if services_tls_runtime[service_name] == "go":
                expected_negotiable.difference_update(NON_FIPS_GROUPS)
        if service_name == CONSOLE_PLUGIN_SERVICE_NAME:
            expected_negotiable.difference_update(NON_FIPS_GROUPS)

        for group, negotiated in group_status.items():
            with subtests.test(msg=f"{service_name}-{group}"):
                # Reachability is asserted for every service, including pending ones:
                # None means the probe saw neither a successful handshake nor a rejection.
                assert negotiated is not None, f"Service {service_name} is unreachable for curve {group}"
                if pending:
                    continue
                if group in expected_negotiable:
                    assert negotiated, f"Service {service_name} must negotiate configured curve {group}"
                else:
                    assert not negotiated, f"Service {service_name} must reject curve {group} (omitted or stripped)"
