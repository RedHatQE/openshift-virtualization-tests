import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt

from tests.install_upgrade_operators.constants import (
    DEVELOPER_CONFIGURATION,
    FEATUREGATES,
    KEY_PATH_SEPARATOR,
)
from tests.install_upgrade_operators.utils import get_resource_key_value
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.virt import get_hyperconverged_kubevirt

LOGGER = logging.getLogger(__name__)

pytestmark = [pytest.mark.sno, pytest.mark.s390x, pytest.mark.skip_must_gather_collection]

KUBEVIRT_FEATUREGATES_KEY = (
    f"configuration{KEY_PATH_SEPARATOR}{DEVELOPER_CONFIGURATION}{KEY_PATH_SEPARATOR}{FEATUREGATES}"
)
CDI_FEATUREGATES_KEY = f"config{KEY_PATH_SEPARATOR}{FEATUREGATES}"


class TestHardcodedFeatureGates:
    @pytest.mark.polarion("CNV-6427")
    def test_managed_cr_featuregate_reconcile_kubevirt(self, admin_client, hco_namespace):
        kubevirt_resource = get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)
        featuregates_before = get_resource_key_value(resource=kubevirt_resource, key_name=KUBEVIRT_FEATUREGATES_KEY)
        assert featuregates_before, "KubeVirt featureGates are empty before reconciliation test"
        expected = set(featuregates_before)
        LOGGER.info(f"KubeVirt featureGates before deletion: {expected}")

        with ResourceEditorValidateHCOReconcile(
            patches={
                kubevirt_resource: {"spec": {"configuration": {"developerConfiguration": {"featureGates": None}}}}
            },
            action="replace",
            list_resource_reconcile=[KubeVirt],
            wait_for_reconcile_post_update=True,
        ):
            kubevirt_resource.reload()
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
            patches={cdi_resource_scope_function: {"spec": {}}},
            action="replace",
            list_resource_reconcile=[CDI],
            wait_for_reconcile_post_update=True,
        ):
            cdi_resource_scope_function.reload()
            actual = get_resource_key_value(resource=cdi_resource_scope_function, key_name=CDI_FEATUREGATES_KEY)
            if isinstance(actual, list):
                actual = set(actual)
            assert actual == expected, f"CDI featureGates not reconciled. Expected: {expected}, actual: {actual}"
