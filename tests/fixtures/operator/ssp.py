import pytest

import utilities.hco
from utilities.constants.hco import SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
from utilities.ssp import get_ssp_resource


@pytest.fixture()
def ssp_resource_scope_function(admin_client, hco_namespace):
    return get_ssp_resource(admin_client=admin_client, namespace=hco_namespace)


@pytest.fixture(scope="class")
def ssp_resource_scope_class(admin_client, hco_namespace):
    return get_ssp_resource(admin_client=admin_client, namespace=hco_namespace)


@pytest.fixture()
def disabled_common_boot_image_import_hco_spec_scope_function(
    admin_client,
    hyperconverged_resource_scope_function,
    golden_images_namespace,
    golden_images_data_import_crons_scope_function,
):
    yield from utilities.hco.disable_common_boot_image_import_hco_spec(
        admin_client=admin_client,
        hco_resource=hyperconverged_resource_scope_function,
        golden_images_namespace=golden_images_namespace,
        golden_images_data_import_crons=golden_images_data_import_crons_scope_function,
    )


@pytest.fixture(scope="class")
def disabled_common_boot_image_import_hco_spec_scope_class(
    admin_client,
    hyperconverged_resource_scope_class,
    golden_images_namespace,
    golden_images_data_import_crons_scope_class,
):
    yield from utilities.hco.disable_common_boot_image_import_hco_spec(
        admin_client=admin_client,
        hco_resource=hyperconverged_resource_scope_class,
        golden_images_namespace=golden_images_namespace,
        golden_images_data_import_crons=golden_images_data_import_crons_scope_class,
    )


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
