import logging

import pytest

from tests.install_upgrade_operators.cert_renewal.utils import (
    verify_certificates_dates_identical_to_initial_dates,
    wait_for_certificates_renewal,
)
from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_DURATION_KEY,
    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY,
)
from utilities.constants import QUARANTINED

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]

LOGGER = logging.getLogger(__name__)


@pytest.mark.xfail(
    reason=(f"{QUARANTINED}: certificate order is messed up sometimes, causing flakiness. tracked in CNV-49628"),
    run=False,
)
class TestCertRotation:
    @pytest.mark.polarion("CNV-6203")
    @pytest.mark.parametrize(
        "hyperconverged_resource_certconfig_change",
        [
            pytest.param({
                HCO_CR_CERT_CONFIG_DURATION_KEY: "11m",
                HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: "10m",
            }),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_certificate_renewed_in_hco(
        self,
        hco_namespace,
        hyperconverged_resource_certconfig_change,
        tmpdir,
        initial_certificates_dates,
        secrets_with_non_closed_bugs,
    ):
        """
        The test verifies the proper certificate rotation/renewal in high-level, that is using the openssl command with
        the -checkend command argument.
        There are 3 steps:
        1. Get the initial certificates dates.
        2. Verify that the certificates will expire beyond the configured certConfig duration time.
        3. Verify that the certificates do not expire before they are supposed to, not renewed before they are supposed
        to.
        4. Then, it waits until the certificates are renewed, verifying that the new certificates dates are different
        from the initial ones.
        """
        LOGGER.info("Verify that the certificate will expire beyond the configured duration time")
        certificates_not_expired = [
            certificate
            for certificate, certificate_data in initial_certificates_dates.items()
            if certificate_data["checkend_result"] != "Certificate will expire"
        ]
        assert not certificates_not_expired, (
            f"Some certificates will not expire: certificates={certificates_not_expired}"
        )

        verify_certificates_dates_identical_to_initial_dates(
            hco_namespace=hco_namespace,
            initial_certificates_dates=initial_certificates_dates,
            secrets_to_skip=secrets_with_non_closed_bugs,
            tmpdir=tmpdir,
        )
        wait_for_certificates_renewal(
            hco_namespace=hco_namespace,
            initial_certificates_dates=initial_certificates_dates,
            secrets_to_skip=secrets_with_non_closed_bugs,
            tmpdir=tmpdir,
        )
