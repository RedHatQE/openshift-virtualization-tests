import pytest
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.constants import (
    DEVELOPER_CONFIGURATION,
    EXPECTED_CDI_HARDCODED_FEATUREGATES,
    EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
    FEATUREGATES,
    KEY_PATH_SEPARATOR,
    RESOURCE_NAME_STR,
    RESOURCE_NAMESPACE_STR,
    RESOURCE_TYPE_STR,
)
from tests.install_upgrade_operators.utils import get_resource_key_value
from utilities.constants import (
    CDI_KUBEVIRT_HYPERCONVERGED,
    KUBEVIRT_KUBEVIRT_HYPERCONVERGED,
)

pytestmark = pytest.mark.sno


class TestHardcodedFeatureGates:
    @pytest.mark.parametrize(
        ("updated_resource", "expected_value", "key_name"),
        [
            pytest.param(
                {
                    RESOURCE_TYPE_STR: KubeVirt,
                    RESOURCE_NAME_STR: KUBEVIRT_KUBEVIRT_HYPERCONVERGED,
                    RESOURCE_NAMESPACE_STR: py_config["hco_namespace"],
                    "patch": {"spec": {"configuration": {"developerConfiguration": {"featureGates": None}}}},
                },
                EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
                f"configuration{KEY_PATH_SEPARATOR}{DEVELOPER_CONFIGURATION}{KEY_PATH_SEPARATOR}{FEATUREGATES}",
                marks=pytest.mark.polarion("CNV-6427"),
                id="delete_featuregates_kubevirt_cr",
            ),
            pytest.param(
                {
                    RESOURCE_TYPE_STR: CDI,
                    RESOURCE_NAME_STR: CDI_KUBEVIRT_HYPERCONVERGED,
                    "patch": {"spec": {}},
                },
                EXPECTED_CDI_HARDCODED_FEATUREGATES,
                f"config{KEY_PATH_SEPARATOR}{FEATUREGATES}",
                marks=(pytest.mark.polarion("CNV-6640")),
                id="delete_featuregates_cdi_cr",
            ),
        ],
        indirect=["updated_resource"],
    )
    @pytest.mark.s390x
    def test_managed_cr_featuregate_reconcile(
        self,
        updated_resource,
        expected_value,
        key_name,
    ):
        actual_value = get_resource_key_value(resource=updated_resource, key_name=key_name)
        assert sorted(actual_value) == sorted(expected_value), (
            f"For {updated_resource.name}, actual featuregates:"
            f" {actual_value} does not match expected "
            f"featuregates: {expected_value}"
        )
