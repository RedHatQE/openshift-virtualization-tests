import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from pytest_testconfig import config as py_config

from tests.install_upgrade_operators.constants import (
    DEVELOPER_CONFIGURATION,
    EXPECTED_CDI_HARDCODED_FEATUREGATES,
    EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
    FEATUREGATES,
    HCO_DEFAULT_FEATUREGATES,
    KEY_NAME_STR,
    KEY_PATH_SEPARATOR,
    RESOURCE_NAME_STR,
    RESOURCE_NAMESPACE_STR,
    RESOURCE_TYPE_STR,
)
from tests.install_upgrade_operators.utils import (
    get_resource_by_name,
    get_resource_key_value,
)
from utilities.constants import CDI_KUBEVIRT_HYPERCONVERGED, KUBEVIRT_HCO_NAME
from utilities.infra import is_jira_open

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def resource_object_value_by_key(request):
    resource_obj = get_resource_by_name(
        resource_kind=request.param.get(RESOURCE_TYPE_STR),
        name=request.param.get(RESOURCE_NAME_STR),
        namespace=request.param.get(RESOURCE_NAMESPACE_STR),
    )
    return get_resource_key_value(resource=resource_obj, key_name=request.param.get(KEY_NAME_STR))


@pytest.mark.parametrize(
    ("expected", "resource_object_value_by_key"),
    [
        pytest.param(
            HCO_DEFAULT_FEATUREGATES,
            {
                RESOURCE_TYPE_STR: HyperConverged,
                RESOURCE_NAME_STR: py_config["hco_cr_name"],
                RESOURCE_NAMESPACE_STR: py_config["hco_namespace"],
                KEY_NAME_STR: FEATUREGATES,
            },
            marks=(pytest.mark.polarion("CNV-6115"),),
            id="verify_default_featuregates_hco_cr",
        ),
        pytest.param(
            EXPECTED_CDI_HARDCODED_FEATUREGATES,
            {
                RESOURCE_TYPE_STR: CDI,
                RESOURCE_NAME_STR: CDI_KUBEVIRT_HYPERCONVERGED,
                KEY_NAME_STR: f"config{KEY_PATH_SEPARATOR}{FEATUREGATES}",
            },
            marks=(pytest.mark.polarion("CNV-6448"),),
            id="verify_defaults_featuregates_cdi_cr",
        ),
        pytest.param(
            EXPECTED_KUBEVIRT_HARDCODED_FEATUREGATES,
            {
                RESOURCE_TYPE_STR: KubeVirt,
                RESOURCE_NAME_STR: KUBEVIRT_HCO_NAME,
                RESOURCE_NAMESPACE_STR: py_config["hco_namespace"],
                KEY_NAME_STR: f"configuration{KEY_PATH_SEPARATOR}{DEVELOPER_CONFIGURATION}"
                f"{KEY_PATH_SEPARATOR}{FEATUREGATES}",
            },
            marks=(pytest.mark.polarion("CNV-6426"),),
            id="verify_defaults_featuregates_kubevirt_cr",
        ),
    ],
    indirect=["resource_object_value_by_key"],
)
@pytest.mark.s390x
def test_default_featuregates_by_resource(
    expected,
    resource_object_value_by_key,
):
    error_message = f"Expected featuregates: {expected}, actual: {resource_object_value_by_key}"
    if isinstance(expected, list):
        assert sorted(expected) == sorted(resource_object_value_by_key), error_message
    else:
        if is_jira_open(jira_id="CNV-63030"):
            LOGGER.warning("Applying workaround: removed ‘autoResourceLimits’ due to open Jira CNV-63030")
            resource_object_value_by_key.pop("autoResourceLimits", None)
        assert expected == resource_object_value_by_key, error_message
