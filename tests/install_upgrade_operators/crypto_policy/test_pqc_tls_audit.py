"""
PQC TLS audit tests for CNV endpoints.

Epic: https://redhat.atlassian.net/browse/CNV-74453
"""

import logging

import pytest

from utilities.constants import HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD
from utilities.jira import is_jira_open

LOGGER = logging.getLogger(__name__)
pytestmark = pytest.mark.post_upgrade


@pytest.mark.polarion("CNV-15222")
def test_cnv_services_pqc_key_exchange(subtests, fips_enabled_cluster, pqc_status_by_service, services_tls_runtime):
    """
    Test that every CNV service negotiates PQC key exchange.

    Preconditions:
        - AAQ enabled
        - Template feature gate enabled with virt-template deployments ready
        - NetworkPolicy allowing test access to console-plugin pods
        - Worker node OpenSSL supports PQC groups
        - All CNV services with a clusterIP discovered
        - TLS runtime type (Go/OpenSSL) detected for each service

    Steps:
        1. For each CNV service, probe PQC key exchange using post-quantum TLS groups
           (X25519MLKEM768, SecP256r1MLKEM768, SecP384r1MLKEM1024)

    Expected:
        - No service is unreachable
        - On non-FIPS clusters: every service accepts PQC with at least one group
        - On FIPS clusters: Go services reject PQC (ML-KEM not FIPS-certified),
          OpenSSL services accept PQC with NIST curves
    """
    for service_name, accepted in pqc_status_by_service.items():
        with subtests.test(msg=service_name):
            if service_name == HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD:
                pytest.xfail(f"CNV-82351: {service_name} — plaintext HTTP behind TLS route, TLS planned for 5.0")
            if service_name == "kubevirt-migration-prometheus" and is_jira_open(jira_id="CNV-87302"):
                pytest.xfail(f"{service_name} — known bug: CNV-87302")
            assert accepted is not None, f"Service {service_name} is unreachable"
            if fips_enabled_cluster:
                runtime = services_tls_runtime.get(service_name, "go")
                if runtime == "go":
                    assert not accepted, f"Go FIPS service {service_name} accepted PQC but must reject"
                else:
                    assert accepted, (
                        f"OpenSSL service {service_name} rejected PQC on FIPS but should accept NIST curves"
                    )
            else:
                assert accepted, f"Service {service_name} rejected PQC but must accept on non-FIPS cluster"
