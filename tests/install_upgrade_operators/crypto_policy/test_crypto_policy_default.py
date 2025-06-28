import logging

import pytest
from ocp_resources.api_server import APIServer
from ocp_resources.cdi import CDI
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.ssp import SSP
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.constants import (
    KEY_NAME_STR,
    RESOURCE_NAME_STR,
    RESOURCE_NAMESPACE_STR,
    RESOURCE_TYPE_STR,
)
from tests.install_upgrade_operators.crypto_policy.constants import (
    CRYPTO_POLICY_EXPECTED_DICT,
    KUBEVIRT_TLS_CONFIG_STR,
    MIN_TLS_VERSIONS,
    TLS_INTERMEDIATE_POLICY,
)
from tests.install_upgrade_operators.crypto_policy.utils import (
    assert_tls_version_connection,
)
from utilities.constants import (
    CDI_KUBEVIRT_HYPERCONVERGED,
    CLUSTER,
    KUBEVIRT_HCO_NAME,
    SSP_KUBEVIRT_HYPERCONVERGED,
    TLS_SECURITY_PROFILE,
)

LOGGER = logging.getLogger(__name__)
pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.mark.parametrize(
    ("resource_crypto_policy_settings", "resource_type"),
    [
        pytest.param(
            {
                RESOURCE_TYPE_STR: APIServer,
                RESOURCE_NAME_STR: CLUSTER,
                KEY_NAME_STR: TLS_SECURITY_PROFILE,
            },
            APIServer,
            marks=(pytest.mark.polarion("CNV-9328")),
            id="test_default_crypto_policy_api_server",
        ),
        pytest.param(
            {
                RESOURCE_TYPE_STR: HyperConverged,
                RESOURCE_NAME_STR: py_config["hco_cr_name"],
                RESOURCE_NAMESPACE_STR: py_config["hco_namespace"],
                KEY_NAME_STR: TLS_SECURITY_PROFILE,
            },
            HyperConverged,
            marks=(pytest.mark.polarion("CNV-9464")),
            id="test_default_crypto_policy_hyperconverged",
        ),
        pytest.param(
            {
                RESOURCE_TYPE_STR: KubeVirt,
                RESOURCE_NAME_STR: KUBEVIRT_HCO_NAME,
                RESOURCE_NAMESPACE_STR: py_config["hco_namespace"],
                KEY_NAME_STR: KUBEVIRT_TLS_CONFIG_STR,
            },
            KubeVirt,
            marks=(pytest.mark.polarion("CNV-9465")),
            id="test_default_crypto_policy_kubevirt",
        ),
        pytest.param(
            {
                RESOURCE_TYPE_STR: SSP,
                RESOURCE_NAME_STR: SSP_KUBEVIRT_HYPERCONVERGED,
                RESOURCE_NAMESPACE_STR: py_config["hco_namespace"],
                KEY_NAME_STR: TLS_SECURITY_PROFILE,
            },
            SSP,
            marks=(pytest.mark.polarion("CNV-9466")),
            id="test_default_crypto_policy_ssp",
        ),
        pytest.param(
            {
                RESOURCE_TYPE_STR: CDI,
                RESOURCE_NAME_STR: CDI_KUBEVIRT_HYPERCONVERGED,
                KEY_NAME_STR: f"config->{TLS_SECURITY_PROFILE}",
            },
            CDI,
            marks=(pytest.mark.polarion("CNV-9467")),
            id="test_default_crypto_policy_cdi",
        ),
        pytest.param(
            {
                RESOURCE_TYPE_STR: NetworkAddonsConfig,
                RESOURCE_NAME_STR: CLUSTER,
                KEY_NAME_STR: TLS_SECURITY_PROFILE,
            },
            NetworkAddonsConfig,
            marks=(pytest.mark.polarion("CNV-9468")),
            id="test_default_crypto_policy_cnao",
        ),
    ],
    indirect=["resource_crypto_policy_settings"],
)
@pytest.mark.s390x
def test_default_crypto_policy(resource_crypto_policy_settings, resource_type):
    expected_result = CRYPTO_POLICY_EXPECTED_DICT[TLS_INTERMEDIATE_POLICY].get(resource_type)
    assert resource_crypto_policy_settings == expected_result, (
        f"For {resource_type.kind}, actual crypto setting found is={resource_crypto_policy_settings},"
        f"expected crypto policy settings={expected_result},"
    )


@pytest.mark.polarion("CNV-9266")
@pytest.mark.s390x
def test_default_crypto_policy_check_connectivity(
    workers, workers_utility_pods, services_to_check_connectivity, fips_enabled_cluster
):
    assert_tls_version_connection(
        utility_pods=workers_utility_pods,
        node=workers[0],
        services=services_to_check_connectivity,
        minimal_version=MIN_TLS_VERSIONS[TLS_INTERMEDIATE_POLICY],
        fips_enabled=fips_enabled_cluster,
    )
