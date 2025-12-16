import logging

import pytest
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.crypto_policy.constants import (
    TLS_CUSTOM_PROFILE,
    TLS_OLD_PROFILE,
)
from tests.install_upgrade_operators.crypto_policy.utils import (
    get_resources_crypto_policy_dict,
    set_hco_crypto_policy,
    update_apiserver_crypto_policy,
)
from utilities.constants import TIMEOUT_2MIN, TIMEOUT_10SEC

LOGGER = logging.getLogger(__name__)
pytestmark = pytest.mark.tier3


@pytest.fixture()
def updated_hco_tls_custom_policy(hyperconverged_resource_scope_function):
    with set_hco_crypto_policy(
        hco_resource=hyperconverged_resource_scope_function,
        tls_spec=TLS_CUSTOM_PROFILE,
    ):
        yield


@pytest.fixture()
def expected_all_managed_crs_crypto_policies(resources_dict, admin_client):
    return get_resources_crypto_policy_dict(
        resources_dict=resources_dict,
        client=admin_client,
    )


@pytest.fixture()
def updated_apiserver_with_tls_old_profile(
    admin_client,
    hco_namespace,
    api_server,
):
    with update_apiserver_crypto_policy(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        apiserver=api_server,
        tls_spec=TLS_OLD_PROFILE,
    ):
        yield


@pytest.mark.jira("RHSTOR-6566", run=False)  # <skip-jira-utils-check>
@pytest.mark.polarion("CNV-9368")
def test_hco_overriding_apiserver_crypto_policy(
    admin_client,
    resources_dict,
    updated_hco_tls_custom_policy,
    expected_all_managed_crs_crypto_policies,
    updated_apiserver_with_tls_old_profile,
):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_10SEC,
        func=get_resources_crypto_policy_dict,
        resources_dict=resources_dict,
        client=admin_client,
    )
    try:
        for sample in sampler:
            if sample != expected_all_managed_crs_crypto_policies:
                conflicting_resources = {
                    resource.kind: crypto_policy
                    for resource, crypto_policy in sample.items()
                    if expected_all_managed_crs_crypto_policies[resource] != sample[resource]
                }
                assert not conflicting_resources, (
                    "API server crypto policy overrides HCO crypto policy\n"
                    f"Actual crypto policy of inconsistent CRs: {conflicting_resources}\n"
                    f"Expected crypto policy of CRs: {expected_all_managed_crs_crypto_policies}\n"
                )
    except TimeoutExpiredError:
        LOGGER.info("API server crypto policy doesn't override HCO crypto policy")
