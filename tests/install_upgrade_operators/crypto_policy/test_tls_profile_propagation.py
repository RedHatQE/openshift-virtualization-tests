"""
TLS profile propagation tests for CNV endpoints.

Epic: https://redhat.atlassian.net/browse/CNV-74453
"""

import pytest


class TestTlsProfilePropagation:
    @pytest.mark.polarion("CNV-11553")
    def test_modern_profile_propagates_to_cnv_services(self, subtests, tls12_status_under_modern_profile):
        """Verify that changing the apiserver TLS profile to Modern propagates to CNV services."""
        for service_name, accepts_tls12 in tls12_status_under_modern_profile.items():
            with subtests.test(msg=service_name):
                assert not accepts_tls12, f"Service {service_name} still accepts TLS 1.2 under Modern profile"
