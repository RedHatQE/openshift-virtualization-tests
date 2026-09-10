import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.install_upgrade_operators.constants import (
    MEDIATED_DEVICES_CONFIGURATION,
)
from utilities.constants.hco import DISABLE_MDEV_CONFIGURATION
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    hco_feature_gates_patch,
    is_feature_gate_enabled,
)

pytestmark = [pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


@pytest.fixture()
def updated_fg_hco(
    admin_client,
    hyperconverged_resource_scope_function,
):
    with ResourceEditorValidateHCOReconcile(
        admin_client=admin_client,
        patches={
            hyperconverged_resource_scope_function: hco_feature_gates_patch(
                hco_resource=hyperconverged_resource_scope_function,
                enable=[DISABLE_MDEV_CONFIGURATION],
            )
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.mark.polarion("CNV-10091")
def test_enable_fg_disable_mdev_config_hco(
    updated_fg_hco,
    hyperconverged_resource_scope_function,
    kubevirt_resource,
):
    assert is_feature_gate_enabled(
        hco_resource=hyperconverged_resource_scope_function,
        name=DISABLE_MDEV_CONFIGURATION,
    ), f"HCO featureGates.{DISABLE_MDEV_CONFIGURATION} is not enabled"

    kubevirt_mdev_enabled = kubevirt_resource.instance.spec["configuration"][MEDIATED_DEVICES_CONFIGURATION]["enabled"]
    assert kubevirt_mdev_enabled is False, (
        f"KubeVirt {MEDIATED_DEVICES_CONFIGURATION}.enabled: {kubevirt_mdev_enabled}, expected: False"
    )
