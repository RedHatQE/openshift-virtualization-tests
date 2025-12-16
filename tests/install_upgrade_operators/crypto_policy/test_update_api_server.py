import logging

import pytest
from ocp_resources.api_server import APIServer
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.crypto_policy.constants import (
    MIN_TLS_VERSIONS,
    TLS_CUSTOM_CIPHERS,
)
from tests.install_upgrade_operators.crypto_policy.utils import (
    assert_crypto_policy_propagated_to_components,
    assert_no_crypto_policy_in_hco,
    assert_tls_ciphers_blocked,
    assert_tls_version_connection,
)
from utilities.constants import TLS_CUSTOM_POLICY, TLS_OLD_POLICY

pytestmark = pytest.mark.tier3

LOGGER = logging.getLogger(__name__)


@pytest.mark.jira("RHSTOR-6566", run=False)  # <skip-jira-utils-check>
@pytest.mark.polarion("CNV-9330")
def test_update_api_server(
    admin_client,
    hco_namespace,
    workers,
    workers_utility_pods,
    cnv_crypto_policy_matrix__function__,
    resources_dict,
    updated_api_server_crypto_policy,
    fips_enabled_cluster,
    services_to_check_connectivity,
):
    LOGGER.info(f"Validating crypto policy {cnv_crypto_policy_matrix__function__} settings on APIServer.")
    assert_crypto_policy_propagated_to_components(
        crypto_policy=cnv_crypto_policy_matrix__function__,
        resources_dict=resources_dict,
        updated_resource_kind=APIServer.kind,
        client=admin_client,
    )
    assert_no_crypto_policy_in_hco(
        crypto_policy=cnv_crypto_policy_matrix__function__,
        hco_namespace=hco_namespace.name,
        hco_name=py_config["hco_cr_name"],
        client=admin_client,
    )

    # Old profile works only on non-FIPS cluster
    if not fips_enabled_cluster or cnv_crypto_policy_matrix__function__ != TLS_OLD_POLICY:
        assert_tls_version_connection(
            utility_pods=workers_utility_pods,
            node=workers[0],
            services=services_to_check_connectivity,
            minimal_version=MIN_TLS_VERSIONS[cnv_crypto_policy_matrix__function__],
            fips_enabled=fips_enabled_cluster,
        )

    # check ciphers only for Custom profile
    if cnv_crypto_policy_matrix__function__ == TLS_CUSTOM_POLICY:
        assert_tls_ciphers_blocked(
            utility_pods=workers_utility_pods,
            node=workers[0],
            services=services_to_check_connectivity,
            tls_version=MIN_TLS_VERSIONS[TLS_CUSTOM_POLICY],
            allowed_ciphers=TLS_CUSTOM_CIPHERS,
        )
