import logging

import pytest
from ocp_resources.hyperconverged import HyperConverged

from tests.install_upgrade_operators.crypto_policy.constants import (
    CRYPTO_POLICY_SPEC_DICT,
)
from tests.install_upgrade_operators.crypto_policy.utils import (
    assert_crypto_policy_propagated_to_components,
    set_hco_crypto_policy,
)
from utilities.constants import TLS_SECURITY_PROFILE

LOGGER = logging.getLogger(__name__)
pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.s390x]


@pytest.fixture()
def hco_crypto_policy(hyperconverged_resource_scope_function, updated_hco_crypto_policy):
    tls_profile = hyperconverged_resource_scope_function.instance.spec.get(TLS_SECURITY_PROFILE)
    return tls_profile.to_dict() if tls_profile else None


@pytest.fixture()
def updated_hco_crypto_policy(
    hyperconverged_resource_scope_function,
    cnv_crypto_policy_matrix__function__,
):
    with set_hco_crypto_policy(
        hco_resource=hyperconverged_resource_scope_function,
        tls_spec=CRYPTO_POLICY_SPEC_DICT[cnv_crypto_policy_matrix__function__],
    ):
        yield


@pytest.mark.polarion("CNV-9331")
def test_set_hco_crypto_policy(
    admin_client,
    cnv_crypto_policy_matrix__function__,
    updated_hco_crypto_policy,
    hco_crypto_policy,
    resources_dict,
):
    expected_hco_crypto_policy = CRYPTO_POLICY_SPEC_DICT[cnv_crypto_policy_matrix__function__]
    assert hco_crypto_policy == expected_hco_crypto_policy, (
        f"Current HCO crypto policy: '{hco_crypto_policy}'\n "
        f"Expected HCO crypto policy: '{expected_hco_crypto_policy}'\n"
    )
    assert_crypto_policy_propagated_to_components(
        crypto_policy=cnv_crypto_policy_matrix__function__,
        resources_dict=resources_dict,
        updated_resource_kind=HyperConverged.kind,
        admin_client=admin_client,
    )
