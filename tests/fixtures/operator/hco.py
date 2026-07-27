import logging

import pytest
from ocp_resources.catalog_source import CatalogSource
from pytest_testconfig import config as py_config

import utilities.hco
from utilities.constants.hco import SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
from utilities.infra import get_hyperconverged_resource

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def hco_namespace(admin_client, installing_cnv):
    if not installing_cnv:
        return utilities.hco.get_hco_namespace(admin_client=admin_client, namespace=py_config["hco_namespace"])


@pytest.fixture()
def hyperconverged_resource_scope_function(admin_client, hco_namespace):
    return get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture(scope="class")
def hyperconverged_resource_scope_class(admin_client, hco_namespace):
    return get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture(scope="module")
def hyperconverged_resource_scope_module(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture(scope="package")
def hyperconverged_resource_scope_package(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture(scope="session")
def hyperconverged_resource_scope_session(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture(scope="class")
def hyperconverged_with_node_placement(request, admin_client, hco_namespace, hyperconverged_resource_scope_class):
    """
    Update HCO CR with infrastructure and workloads spec.
    """
    infra_placement = request.param["infra"]
    workloads_placement = request.param["workloads"]

    LOGGER.info("Fetching HCO to save its initial node placement configuration ")
    initial_infra = hyperconverged_resource_scope_class.instance.to_dict()["spec"].get("infra", {})
    initial_workloads = hyperconverged_resource_scope_class.instance.to_dict()["spec"].get("workloads", {})
    yield utilities.hco.apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_class,
        hco_namespace=hco_namespace,
        infra_placement=infra_placement,
        workloads_placement=workloads_placement,
    )
    LOGGER.info("Revert to initial HCO node placement configuration ")
    utilities.hco.apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_class,
        hco_namespace=hco_namespace,
        infra_placement=initial_infra,
        workloads_placement=initial_workloads,
    )


@pytest.fixture()
def hco_spec(hyperconverged_resource_scope_function):
    return hyperconverged_resource_scope_function.instance.to_dict()["spec"]


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


@pytest.fixture(scope="session")
def hco_image(
    admin_client,
    installing_cnv,
    cnv_subscription_scope_session,
):
    if installing_cnv:
        return "CNV not yet installed."
    source_name = cnv_subscription_scope_session.instance.spec.source
    for cs in CatalogSource.get(
        client=admin_client,
        name=source_name,
        namespace=py_config["marketplace_namespace"],
    ):
        return cs.instance.spec.image


@pytest.fixture(scope="module")
def hco_status_related_objects(hyperconverged_resource_scope_module):
    """
    Gets HCO.status.relatedObjects list
    """
    return hyperconverged_resource_scope_module.instance.status.relatedObjects


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
