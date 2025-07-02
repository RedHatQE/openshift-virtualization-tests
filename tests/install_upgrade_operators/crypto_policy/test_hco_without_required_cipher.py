import copy
import logging

import pytest
from kubernetes.dynamic.exceptions import ForbiddenError

from tests.install_upgrade_operators.crypto_policy.constants import (
    MANAGED_CRS_LIST,
    TLS_CUSTOM_PROFILE,
)
from utilities.constants import TLS_CUSTOM_POLICY, TLS_SECURITY_PROFILE
from utilities.hco import ResourceEditorValidateHCOReconcile

LOGGER = logging.getLogger(__name__)


@pytest.mark.polarion("CNV-9367")
@pytest.mark.s390x
def test_set_hco_crypto_failed_without_required_cipher(
    hyperconverged_resource_scope_function,
):
    """
    This test validates that the operation is failed with proper error message,
    when hco.spec.tlsSecurityProfile set with 'Custom' profile with TLS 1.2 and
    ciphers without mandatory http/2 required ciphers
    """
    tls_custom_profile = copy.deepcopy(TLS_CUSTOM_PROFILE)
    tls_custom_profile[TLS_CUSTOM_POLICY]["ciphers"] = [
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES256-GCM-SHA384",
    ]
    tls_spec = {"spec": {TLS_SECURITY_PROFILE: tls_custom_profile}}
    with pytest.raises(ForbiddenError, match=r"missing an HTTP/2-required"):
        with ResourceEditorValidateHCOReconcile(
            patches={hyperconverged_resource_scope_function: tls_spec},
            list_resource_reconcile=MANAGED_CRS_LIST,
            wait_for_reconcile_post_update=True,
        ):
            LOGGER.error(
                f"Setting HCO TLS profile without required http/2 ciphers using the spec - {tls_spec} was successful"
            )
