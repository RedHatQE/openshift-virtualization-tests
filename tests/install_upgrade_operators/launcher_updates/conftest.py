import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.install_upgrade_operators.launcher_updates.constants import (
    CUSTOM_WORKLOAD_STRATEGY_SPEC,
)
from utilities.hco import ResourceEditorValidateHCOReconcile


@pytest.fixture()
def updated_workload_strategy_custom_values(hyperconverged_resource_scope_function, admin_client, hco_namespace):
    """
    This fixture updates HCO CR with custom values for spec.workloadUpdateStrategy
    Note: This is needed for tests that modify such fields to default values
    """
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: CUSTOM_WORKLOAD_STRATEGY_SPEC.copy()},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield
