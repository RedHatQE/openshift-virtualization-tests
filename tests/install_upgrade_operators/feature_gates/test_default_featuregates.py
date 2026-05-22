import pytest

from tests.install_upgrade_operators.constants import (
    EXPECTED_CDI_HARDCODED_FEATUREGATES,
    EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
    FEATUREGATES,
    HCO_DEFAULT_FEATUREGATES,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


@pytest.fixture()
def hco_featuregates(hco_spec):
    return hco_spec[FEATUREGATES]


@pytest.mark.parametrize(
    ("expected_value", "featuregates_fixture"),
    [
        pytest.param(
            HCO_DEFAULT_FEATUREGATES,
            "hco_featuregates",
            marks=(pytest.mark.polarion("CNV-6115"),),
            id="verify_default_featuregates_hco_cr",
        ),
        pytest.param(
            EXPECTED_CDI_HARDCODED_FEATUREGATES,
            "cdi_feature_gates",
            marks=(pytest.mark.polarion("CNV-6448"),),
            id="verify_defaults_featuregates_cdi_cr",
        ),
        pytest.param(
            EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
            "kubevirt_feature_gates",
            marks=(pytest.mark.polarion("CNV-6426"),),
            id="verify_defaults_featuregates_kubevirt_cr",
        ),
    ],
    indirect=["expected_value"],
)
def test_default_featuregates_by_resource(
    request,
    expected_value,
    featuregates_fixture,
):
    actual = request.getfixturevalue(featuregates_fixture)
    if isinstance(actual, list):
        actual = set(actual)
    assert expected_value == actual, f"Expected featuregates: {expected_value}, actual: {actual}"
