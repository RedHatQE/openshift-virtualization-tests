import logging

import pytest

from tests.install_upgrade_operators.crypto_policy.constants import (
    PQC_GROUP_SECP256R1_MLKEM768,
    PQC_GROUP_SECP384R1_MLKEM1024,
    PQC_GROUP_X25519_MLKEM768,
)

pytestmark = [pytest.mark.tier3, pytest.mark.iuo, pytest.mark.tls_compliance]

LOGGER = logging.getLogger(__name__)


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
        fips_enabled_cluster,
        services_accepting_pqc,
    ):
        """Verify CNV services handle PQC (X25519MLKEM768) key exchange correctly.

        On non-FIPS clusters with Go 1.25+, services accept X25519MLKEM768.
        On FIPS clusters, services must reject PQC (ML-KEM not FIPS-certified).
        """
        if fips_enabled_cluster:
            assert not services_accepting_pqc, (
                f"Expected all CNV services to reject PQC on FIPS cluster, but these accepted: {services_accepting_pqc}"
            )
        else:
            assert services_accepting_pqc, (
                "Expected CNV services to accept PQC (X25519MLKEM768) on non-FIPS cluster, but all rejected"
            )

    @pytest.mark.polarion("CNV-15224")
    def test_non_fips_services_accept_pqc(
        self,
        fips_enabled_cluster,
        services_accepting_pqc,
    ):
        """Verify non-FIPS CNV services accept PQC key exchange (CNV-74453 PQC readiness).

        On non-FIPS clusters with Go 1.25+, services accept X25519MLKEM768.
        On FIPS clusters, PQC is not expected (ML-KEM not yet FIPS 140-3 certified).
        """
        if fips_enabled_cluster:
            pytest.xfail(reason="FIPS clusters do not support PQC: ML-KEM is not FIPS 140-3 certified")

        LOGGER.info(f"Services that accepted PQC: {services_accepting_pqc}")
        assert services_accepting_pqc, (
            "Expected CNV services to accept PQC key exchange (X25519MLKEM768) on non-FIPS cluster"
        )
