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
from utilities.constants.components import (
    CDI_KUBEVIRT_HYPERCONVERGED,
    KUBEVIRT_KUBEVIRT_HYPERCONVERGED,
)

pytestmark = [pytest.mark.sno, pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


class TestHardcodedFeatureGates:
    @pytest.mark.polarion("CNV-6427")
    def test_managed_cr_featuregate_reconcile_kubevirt(self, admin_client, hco_namespace):
        kubevirt_resource = get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)
        featuregates_before = get_resource_key_value(resource=kubevirt_resource, key_name=KUBEVIRT_FEATUREGATES_KEY)
        assert featuregates_before, "KubeVirt featureGates are empty before reconciliation test"
        expected = set(featuregates_before)
        LOGGER.info(f"KubeVirt featureGates before deletion: {expected}")

        with ResourceEditorValidateHCOReconcile(
            admin_client=admin_client,
            patches={
                kubevirt_resource: {"spec": {"configuration": {"developerConfiguration": {"featureGates": None}}}}
            },
            action="replace",
            list_resource_reconcile=[KubeVirt],
            wait_for_reconcile_post_update=True,
        ):
            actual = get_resource_key_value(resource=kubevirt_resource, key_name=KUBEVIRT_FEATUREGATES_KEY)
            if isinstance(actual, list):
                actual = set(actual)
            assert actual == expected, f"KubeVirt featureGates not reconciled. Expected: {expected}, actual: {actual}"

    @pytest.mark.polarion("CNV-6640")
    def test_managed_cr_featuregate_reconcile_cdi(self, admin_client, cdi_resource_scope_function):
        featuregates_before = get_resource_key_value(
            resource=cdi_resource_scope_function, key_name=CDI_FEATUREGATES_KEY
        )
        assert featuregates_before, "CDI featureGates are empty before reconciliation test"
        expected = set(featuregates_before)
        LOGGER.info(f"CDI featureGates before deletion: {expected}")

        with ResourceEditorValidateHCOReconcile(
            admin_client=admin_client,
            patches={cdi_resource_scope_function: {"spec": {}}},
            action="replace",
            list_resource_reconcile=[CDI],
            wait_for_reconcile_post_update=True,
        ):
            actual = get_resource_key_value(resource=cdi_resource_scope_function, key_name=CDI_FEATUREGATES_KEY)
            if isinstance(actual, list):
                actual = set(actual)
            assert actual == expected, f"CDI featureGates not reconciled. Expected: {expected}, actual: {actual}"
