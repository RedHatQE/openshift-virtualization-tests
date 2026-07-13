import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.install_upgrade_operators.constants import (
    DISABLE_MDEV_CONFIGURATION,
    FEATUREGATES,
    FG_ENABLED,
    MEDIATED_DEVICES_CONFIGURATION,
)
from utilities.hco import ResourceEditorValidateHCOReconcile

pytestmark = [pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


@pytest.fixture()
def updated_fg_hco(
    request,
    hyperconverged_resource_scope_function,
):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: {"spec": {FEATUREGATES: request.param["featuregate"]}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.mark.parametrize(
    "updated_fg_hco",
    [
        pytest.param(
            {"featuregate": {DISABLE_MDEV_CONFIGURATION: FG_ENABLED}},
            marks=pytest.mark.polarion("CNV-10091"),
            id="test_enable_fg_disable_mdev_config_hco",
        ),
    ],
    indirect=["updated_fg_hco"],
)
def test_enable_fg_hco(
    updated_fg_hco,
    hco_spec,
    kubevirt_resource,
):
    assert hco_spec[FEATUREGATES][DISABLE_MDEV_CONFIGURATION] is True, (
        f"HCO featureGates.{DISABLE_MDEV_CONFIGURATION} is not True: {hco_spec[FEATUREGATES]}"
    )

    kubevirt_mdev_enabled = kubevirt_resource.instance.spec["configuration"][MEDIATED_DEVICES_CONFIGURATION]["enabled"]
    assert kubevirt_mdev_enabled is False, (
        f"KubeVirt {MEDIATED_DEVICES_CONFIGURATION}.enabled: {kubevirt_mdev_enabled}, expected: False"
    )
