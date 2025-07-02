import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.install_upgrade_operators.constants import (
    DEVELOPER_CONFIGURATION,
    DISABLE_MDEV_CONFIGURATION,
    FEATUREGATES,
    FG_ENABLED,
)
from utilities.constants import VALUE_STR
from utilities.hco import ResourceEditorValidateHCOReconcile

FEATUREGATE_NAME_KEY_STR = "featuregate_name"


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
    ("updated_fg_hco", "kubevirt_featuregate_name", "hco_featuregate"),
    [
        pytest.param(
            {"featuregate": {DISABLE_MDEV_CONFIGURATION: FG_ENABLED}},
            "DisableMDEVConfiguration",
            {
                FEATUREGATE_NAME_KEY_STR: DISABLE_MDEV_CONFIGURATION,
                VALUE_STR: FG_ENABLED,
            },
            marks=pytest.mark.polarion("CNV-10091"),
            id="test_enable_fg_disable_mdev_config_hco",
        ),
    ],
    indirect=["updated_fg_hco"],
)
@pytest.mark.s390x
def test_enable_fg_hco(
    updated_fg_hco,
    hco_spec,
    kubevirt_resource,
    kubevirt_featuregate_name,
    hco_featuregate,
):
    actual_value = hco_spec[FEATUREGATES][hco_featuregate[FEATUREGATE_NAME_KEY_STR]]
    expected_value = hco_featuregate[VALUE_STR]
    assert actual_value == expected_value, (
        f"Current HCO featuregate {VALUE_STR}: {actual_value}, expected: {expected_value}"
    )

    enabled_featuregates = kubevirt_resource.instance.spec["configuration"][DEVELOPER_CONFIGURATION][FEATUREGATES]
    assert kubevirt_featuregate_name in enabled_featuregates, (
        f"Current Kubevirt featuregate {VALUE_STR}: {enabled_featuregates}, expected: {expected_value}"
    )
