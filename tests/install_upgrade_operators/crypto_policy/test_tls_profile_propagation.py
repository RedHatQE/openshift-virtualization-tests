import logging

import pytest

pytestmark = [pytest.mark.tier3, pytest.mark.tls_compliance]

LOGGER = logging.getLogger(__name__)


class TestTlsProfilePropagation:
    @pytest.mark.polarion("CNV-11553")
    def test_modern_profile_propagates_to_cnv_services(self, services_still_accepting_tls12_under_modern):
        """Verify that changing the apiserver TLS profile to Modern propagates to CNV services."""
        assert not services_still_accepting_tls12_under_modern, (
            f"After applying Modern TLS profile, these CNV services still accept TLS 1.2: "
            f"{services_still_accepting_tls12_under_modern}"
        )
