import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.install_upgrade_operators.constants import (
    FEATUREGATES,
    FG_ENABLED,
    MEDIATED_DEVICES_CONFIGURATION,
)
from utilities.constants.hco import DISABLE_MDEV_CONFIGURATION, HCOv1Spec
from utilities.hco import ResourceEditorValidateHCOReconcile

pytestmark = [pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


@pytest.fixture()
def updated_fg_hco(
    request,
    admin_client,
    hyperconverged_resource_scope_function,
):
    with ResourceEditorValidateHCOReconcile(
        admin_client=admin_client,
        patches={hyperconverged_resource_scope_function: request.param["patch"]},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.mark.parametrize(
    "updated_fg_hco",
    [
        pytest.param(
            {"patch": HCOv1Spec.feature_gates(disableMDevConfiguration=FG_ENABLED)},
            marks=pytest.mark.polarion("CNV-10091"),
            id="test_enable_fg_disable_mdev_config_hco",
        ),
    ],
    indirect=["updated_fg_hco"],
)
def test_enable_fg_hco(
    updated_fg_hco,
    hco_spec,
    hco_fg_phases,
    kubevirt_resource,
):
    fg_list = hco_spec[FEATUREGATES]
    assert HCOv1Spec.is_fg_enabled(feature_gates=fg_list, name=DISABLE_MDEV_CONFIGURATION, fg_phases=hco_fg_phases), (
        f"HCO featureGates.{DISABLE_MDEV_CONFIGURATION} is not enabled: {fg_list}"
    )

    kubevirt_mdev_enabled = kubevirt_resource.instance.spec["configuration"][MEDIATED_DEVICES_CONFIGURATION]["enabled"]
    assert kubevirt_mdev_enabled is False, (
        f"KubeVirt {MEDIATED_DEVICES_CONFIGURATION}.enabled: {kubevirt_mdev_enabled}, expected: False"
    )
