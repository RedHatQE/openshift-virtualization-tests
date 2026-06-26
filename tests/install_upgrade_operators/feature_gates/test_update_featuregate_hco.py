import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.install_upgrade_operators.constants import (
    DEVELOPER_CONFIGURATION,
    DISABLE_MDEV_CONFIGURATION,
    FEATUREGATES,
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
    ("updated_fg_hco", "kubevirt_featuregate_name", "expected_hco_featuregate"),
    [
        pytest.param(
            {"featuregate": [{"name": DISABLE_MDEV_CONFIGURATION}]},
            "DisableMDEVConfiguration",
            {"name": DISABLE_MDEV_CONFIGURATION},
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
    kubevirt_featuregate_name,
    expected_hco_featuregate,
):
    actual_featuregates = hco_spec.get(FEATUREGATES, [])
    assert expected_hco_featuregate in actual_featuregates, (
        f"Expected HCO featuregate {expected_hco_featuregate} not found in: {actual_featuregates}"
    )

    enabled_featuregates = kubevirt_resource.instance.spec["configuration"][DEVELOPER_CONFIGURATION][FEATUREGATES]
    assert kubevirt_featuregate_name in enabled_featuregates, (
        f"KubeVirt featuregate {kubevirt_featuregate_name} not found in: {enabled_featuregates}"
    )
