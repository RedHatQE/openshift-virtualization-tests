import logging

import pytest

from tests.install_upgrade_operators.crypto_policy.constants import (
    PQC_GROUP_SECP256R1_MLKEM768,
    PQC_GROUP_SECP384R1_MLKEM1024,
)

pytestmark = [pytest.mark.tier3, pytest.mark.iuo]

LOGGER = logging.getLogger(__name__)


class TestPqcNodeCapability:
    @pytest.mark.polarion("CNV-15221")
    def test_node_openssl_supports_pqc_groups(
        self,
        node_available_tls_groups,
    ):
        """Verify that worker node OpenSSL supports post-quantum TLS groups."""
        LOGGER.info(f"Available TLS groups on node: {node_available_tls_groups}")
        assert PQC_GROUP_SECP256R1_MLKEM768 in node_available_tls_groups, (
            f"PQC group {PQC_GROUP_SECP256R1_MLKEM768} not found in node TLS groups: {node_available_tls_groups}"
        )
        assert PQC_GROUP_SECP384R1_MLKEM1024 in node_available_tls_groups, (
            f"PQC group {PQC_GROUP_SECP384R1_MLKEM1024} not found in node TLS groups: {node_available_tls_groups}"
        )


class TestPqcCnvEndpoints:
    @pytest.mark.polarion("CNV-15222")
    def test_cnv_services_pqc_with_classical_fallback(
        self,
        services_without_classical_fallback,
    ):
        """Verify CNV services fall back to classical key exchange when PQC is offered with a fallback group."""
        assert not services_without_classical_fallback, (
            f"Expected all CNV services to fall back to classical ECDH, "
            f"but these did not: {services_without_classical_fallback}"
        )

    @pytest.mark.polarion("CNV-15223")
    def test_cnv_services_reject_pqc_only(
        self,
        services_accepting_pqc_only,
    ):
        """Verify CNV services reject TLS handshake when only PQC groups are offered."""
        assert not services_accepting_pqc_only, (
            f"Expected all CNV services to reject PQC-only TLS, but these accepted: {services_accepting_pqc_only}"
        )
