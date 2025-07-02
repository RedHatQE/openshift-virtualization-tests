import logging
from copy import deepcopy

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.resource import Resource
from ocp_resources.ssp import SSP
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.crypto_policy.constants import (
    KUBEVIRT_TLS_CONFIG_KEY,
    TLS_CUSTOM_PROFILE,
    TLS_CUSTOM_PROFILE_KUBEVIRT,
    TLS_INTERMEDIATE_POLICY,
    TLS_MODERN_POLICY,
)
from tests.install_upgrade_operators.crypto_policy.utils import (
    get_resources_crypto_policy_dict,
)
from utilities.constants import (
    DEFAULT_HCO_CONDITIONS,
    TIMEOUT_5MIN,
    TIMEOUT_10SEC,
    TLS_CUSTOM_POLICY,
    TLS_OLD_POLICY,
    TLS_SECURITY_PROFILE,
)
from utilities.hco import (
    is_hco_tainted,
    update_hco_annotations,
    wait_for_hco_conditions,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.arm64]

LOGGER = logging.getLogger(__name__)
TLS_POLICIES_WITHOUT_CUSTOM_POLICY = {
    TLS_OLD_POLICY: None,
    TLS_INTERMEDIATE_POLICY: None,
    TLS_MODERN_POLICY: None,
}


def wait_for_resource_crypto_policy_update(resource, expected_crypto_policy, resources_dict):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_10SEC,
        func=get_resources_crypto_policy_dict,
        resources=[resource],
        resources_dict=resources_dict,
    )
    sample = None
    try:
        for sample in sampler:
            if sample[resource] == expected_crypto_policy:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Failed to set TLS crypto policy for resource: {resource.kind},\n"
            f"Current TLS policy: '{sample[resource]}'\n"
            f"Expected TLS policy: '{expected_crypto_policy}'"
        )
        raise


@pytest.fixture()
def updated_cr_with_custom_crypto_policy(
    request,
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
):
    resource = request.param["resource"]
    value = request.param["value"]
    tls_policy = {**value, **TLS_POLICIES_WITHOUT_CUSTOM_POLICY}
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_function,
        path=request.param["key"],
        value=tls_policy,
        component=request.param["component"],
        resource_list=[resource],
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            expected_conditions={
                **DEFAULT_HCO_CONDITIONS,
                **{"TaintedConfiguration": Resource.Condition.Status.TRUE},
            },
        )
        yield {"resource": resource, "tls_policy": value}
    assert not is_hco_tainted(admin_client=admin_client, hco_namespace=hco_namespace.name)


@pytest.mark.parametrize(
    "updated_cr_with_custom_crypto_policy",
    [
        pytest.param(
            {
                "component": "cdi",
                "resource": CDI,
                "key": TLS_SECURITY_PROFILE,
                "value": deepcopy(TLS_CUSTOM_PROFILE),
            },
            marks=pytest.mark.polarion("CNV-9332"),
            id="test_set_CDI_crypto_policy_using_hco_jsonpatch_annotation",
        ),
        pytest.param(
            {
                "component": "cnao",
                "resource": NetworkAddonsConfig,
                "key": TLS_SECURITY_PROFILE,
                "value": deepcopy(TLS_CUSTOM_PROFILE),
            },
            marks=pytest.mark.polarion("CNV-9380"),
            id="test_set_CNAO_crypto_policy_using_hco_jsonpatch_annotation",
        ),
        pytest.param(
            {
                "component": "kubevirt",
                "resource": KubeVirt,
                "key": KUBEVIRT_TLS_CONFIG_KEY,
                "value": deepcopy(TLS_CUSTOM_PROFILE_KUBEVIRT[TLS_CUSTOM_POLICY]),
            },
            marks=pytest.mark.polarion("CNV-9381"),
            id="test_set_kubevirt_crypto_policy_using_hco_jsonpatch_annotation",
        ),
        pytest.param(
            {
                "component": "ssp",
                "resource": SSP,
                "key": TLS_SECURITY_PROFILE,
                "value": deepcopy(TLS_CUSTOM_PROFILE),
            },
            marks=pytest.mark.polarion("CNV-9676"),
            id="test_set_ssp_crypto_policy_using_hco_jsonpatch_annotation",
        ),
    ],
    indirect=["updated_cr_with_custom_crypto_policy"],
)
@pytest.mark.s390x
def test_update_specific_component_crypto_policy(
    resources_dict,
    updated_cr_with_custom_crypto_policy,
):
    wait_for_resource_crypto_policy_update(
        resource=updated_cr_with_custom_crypto_policy["resource"],
        expected_crypto_policy=updated_cr_with_custom_crypto_policy["tls_policy"],
        resources_dict=resources_dict,
    )
