import pytest

from utilities.constants.hco import SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
from utilities.ssp import get_ssp_resource


@pytest.fixture()
def ssp_resource_scope_function(admin_client, hco_namespace):
    return get_ssp_resource(admin_client=admin_client, namespace=hco_namespace)


@pytest.fixture(scope="class")
def ssp_resource_scope_class(admin_client, hco_namespace):
    return get_ssp_resource(admin_client=admin_client, namespace=hco_namespace)


@pytest.fixture()
def hyperconverged_status_templates_scope_function(
    hyperconverged_resource_scope_function,
):
    return hyperconverged_resource_scope_function.instance.to_dict()["status"][SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME]


@pytest.fixture(scope="module")
def hyperconverged_status_templates_scope_module(
    hyperconverged_resource_scope_module,
):
    return hyperconverged_resource_scope_module.instance.to_dict()["status"][SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME]


@pytest.fixture(scope="class")
def hyperconverged_status_templates_scope_class(
    hyperconverged_resource_scope_class,
):
    return hyperconverged_resource_scope_class.instance.status.dataImportCronTemplates
