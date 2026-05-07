"""
TLS profile propagation tests for CNV endpoints.

Epic: https://redhat.atlassian.net/browse/CNV-74453
"""

import logging

import pytest

from tests.install_upgrade_operators.crypto_policy.constants import (
    TLS_VERSION_1_2,
    TLS_VERSION_1_3,
)
from tests.install_upgrade_operators.crypto_policy.utils import check_service_accepts_tls_version
from utilities.constants import HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD
from utilities.jira import is_jira_open

LOGGER = logging.getLogger(__name__)

SERVICES_WITH_OPEN_BUGS = {
    "hpp-prometheus-metrics": "CNV-82350",
}


@pytest.mark.polarion("CNV-11553")
@pytest.mark.usefixtures("modern_tls_profile_applied", "console_plugin_test_network_policy")
def test_modern_profile_propagates_to_cnv_services(
    subtests, workers_utility_pods, worker_node1, cnv_services_with_template
):
    """
    Test that the Modern TLS profile propagates from the APIServer to all CNV services.

    Preconditions:
        - AAQ enabled
        - Template feature gate enabled with virt-template deployments ready
        - NetworkPolicy allowing test access to console-plugin pods
        - Modern TLS profile applied to the APIServer and propagated to all managed CRs
        - All CNV services with a clusterIP discovered

    Steps:
        1. For each CNV service, attempt a TLS 1.2 connection
        2. For each CNV service, attempt a TLS 1.3 connection

    Expected:
        - Every service rejects TLS 1.2 connections
        - Every service accepts TLS 1.3 connections
    """
    for service in cnv_services_with_template:
        service_name = service.name
        with subtests.test(msg=service_name):
            if service_name == HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD:
                pytest.xfail(f"CNV-82351: {service_name} — plaintext HTTP behind TLS route, TLS planned for 5.0")
            if jira_id := SERVICES_WITH_OPEN_BUGS.get(service_name):
                if is_jira_open(jira_id=jira_id):
                    pytest.xfail(f"{service_name} — known bug: {jira_id}")
            assert not check_service_accepts_tls_version(
                utility_pods=workers_utility_pods,
                node=worker_node1,
                service=service,
                tls_version=TLS_VERSION_1_2,
            ), f"Service {service_name} still accepts TLS 1.2 under Modern profile"
            assert check_service_accepts_tls_version(
                utility_pods=workers_utility_pods,
                node=worker_node1,
                service=service,
                tls_version=TLS_VERSION_1_3,
            ), f"Service {service_name} does not accept TLS 1.3 under Modern profile"
