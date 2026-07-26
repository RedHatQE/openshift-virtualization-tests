import pytest

from tests.install_upgrade_operators.constants import (
    DISABLE_MDEV_CONFIGURATION,
    FEATUREGATES,
    MEDIATED_DEVICES_CONFIGURATION,
)
from utilities.hco import set_hco_feature_gates

pytestmark = [pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


@pytest.fixture()
def updated_fg_hco(
    request,
    hyperconverged_resource_scope_function,
):
    with set_hco_feature_gates(
        hco_resource=hyperconverged_resource_scope_function,
        enable=request.param["enable"],
    ):
        yield


@pytest.mark.parametrize(
    "updated_fg_hco",
    [
        pytest.param(
            {"enable": [DISABLE_MDEV_CONFIGURATION]},
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
    hco_fg_names = {fg["name"] for fg in hco_spec.get(FEATUREGATES, [])}
    assert DISABLE_MDEV_CONFIGURATION in hco_fg_names, (
        f"HCO featureGates does not contain {DISABLE_MDEV_CONFIGURATION}: {hco_spec.get(FEATUREGATES, [])}"
    )

    kubevirt_mdev_enabled = kubevirt_resource.instance.spec["configuration"][MEDIATED_DEVICES_CONFIGURATION]["enabled"]
    assert kubevirt_mdev_enabled is False, (
        f"KubeVirt {MEDIATED_DEVICES_CONFIGURATION}.enabled: {kubevirt_mdev_enabled}, expected: False"
    )
