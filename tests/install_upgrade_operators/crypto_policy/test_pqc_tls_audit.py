"""
PQC TLS audit tests for CNV endpoints.

Epic: https://redhat.atlassian.net/browse/CNV-74453
"""

import logging

import pytest

from tests.install_upgrade_operators.crypto_policy.constants import (
    PQC_GROUP_SECP256R1_MLKEM768,
    PQC_GROUP_SECP384R1_MLKEM1024,
    PQC_GROUP_X25519_MLKEM768,
)
from utilities.constants import HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD
from utilities.jira import is_jira_open

LOGGER = logging.getLogger(__name__)

SERVICES_WITH_OPEN_BUGS = {
    "hpp-prometheus-metrics": "CNV-82350",
    "kubevirt-migration-prometheus": "CNV-83219",
}


class TestPqcNodeCapability:
    @pytest.mark.polarion("CNV-15221")
    def test_node_openssl_supports_pqc_groups(
        self,
        node_available_tls_groups,
    ):
        """Verify that worker node OpenSSL supports post-quantum TLS groups."""
        LOGGER.info(f"Available TLS groups on node: {node_available_tls_groups}")
        missing_groups = [
            group
            for group in [PQC_GROUP_X25519_MLKEM768, PQC_GROUP_SECP256R1_MLKEM768, PQC_GROUP_SECP384R1_MLKEM1024]
            if group not in node_available_tls_groups
        ]
        assert not missing_groups, (
            f"PQC groups not found in node TLS groups: {missing_groups}. Available: {node_available_tls_groups}"
        )


class TestPqcCnvEndpoints:
    @pytest.mark.polarion("CNV-15222")
    def test_cnv_services_pqc_key_exchange(
        self,
        subtests,
        fips_enabled_cluster,
        pqc_status_by_service,
    ):
        """Verify every CNV service negotiates PQC key exchange.

        Probes each service with multiple PQC groups (X25519MLKEM768, SecP256r1MLKEM768,
        SecP384r1MLKEM1024) and passes if any group negotiates successfully.
        On FIPS clusters, all services must reject PQC (ML-KEM not FIPS-certified).
        """
        for service_name, accepted in pqc_status_by_service.items():
            with subtests.test(msg=service_name):
                if service_name == HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD:
                    LOGGER.info(
                        f"CNV-82351: Skipping {service_name} — plaintext HTTP behind TLS route, TLS planned for 5.0"
                    )
                    continue
                if jira_id := SERVICES_WITH_OPEN_BUGS.get(service_name):
                    if is_jira_open(jira_id=jira_id):
                        LOGGER.info(f"Skipping {service_name} — known bug: {jira_id}")
                        continue
                assert accepted is not None, f"Service {service_name} is unreachable"
                if fips_enabled_cluster:
                    assert not accepted, f"Service {service_name} accepted PQC but must reject on FIPS cluster"
                else:
                    assert accepted, f"Service {service_name} rejected PQC but must accept on non-FIPS cluster"
