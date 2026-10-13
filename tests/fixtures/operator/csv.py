import logging

import pytest
from packaging.version import parse
from pytest_testconfig import config as py_config

import utilities.hco
from utilities.constants.hco import HCO_SUBSCRIPTION
from utilities.infra import get_clusterversion, get_subscription
from utilities.operator import disable_default_sources_in_operatorhub, get_hco_csv_name_by_version

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def installing_cnv(pytestconfig):
    return pytestconfig.option.install


@pytest.fixture(scope="session")
def openshift_current_version(admin_client):
    return get_clusterversion(client=admin_client).instance.status.history[0].version


@pytest.fixture(scope="session")
def ocp_current_version(openshift_current_version):
    return parse(version=openshift_current_version.split("-")[0])


@pytest.fixture(scope="session")
def cnv_target_version(pytestconfig):
    return pytestconfig.option.cnv_version


@pytest.fixture(scope="session")
def cnv_channel(pytestconfig):
    return pytestconfig.option.cnv_channel


@pytest.fixture(scope="session")
def hco_target_csv_name(cnv_target_version):
    return get_hco_csv_name_by_version(cnv_target_version=cnv_target_version) if cnv_target_version else None


@pytest.fixture(scope="session")
def cnv_source(pytestconfig):
    return pytestconfig.option.cnv_source or "osbs"


@pytest.fixture(scope="session")
def is_production_source(cnv_source):
    return cnv_source == "production"


@pytest.fixture(scope="session")
def csv_scope_session(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return utilities.hco.get_installed_hco_csv(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="session")
def cnv_current_version(installing_cnv, csv_scope_session):
    if installing_cnv:
        return "CNV not yet installed."
    if csv_scope_session:
        version = csv_scope_session.instance.spec.version
        if not version:
            raise ValueError("CSV spec.version is missing (field is optional in schema).")
        return version


@pytest.fixture(scope="session")
def cnv_subscription_scope_session(
    admin_client,
    installing_cnv,
    hco_namespace,
):
    if not installing_cnv:
        return get_subscription(
            admin_client=admin_client,
            namespace=hco_namespace.name,
            subscription_name=py_config["hco_subscription"] or HCO_SUBSCRIPTION,
        )


@pytest.fixture(scope="session")
def csv_related_images_scope_session(csv_scope_session):
    return csv_scope_session.instance.spec.relatedImages


@pytest.fixture(scope="package")
def must_gather_image_url(csv_scope_session):
    LOGGER.info(f"Csv name is : {csv_scope_session.name}")
    must_gather_image = [
        image["image"] for image in csv_scope_session.instance.spec.relatedImages if "must-gather" in image["name"]
    ]
    assert must_gather_image, (
        f"Csv: {csv_scope_session.name}, "
        f"related images: {csv_scope_session.instance.spec.relatedImages} "
        "does not have must gather image."
    )

    return must_gather_image[0]


@pytest.fixture(scope="module")
def disabled_default_sources_in_operatorhub_scope_module(admin_client, installing_cnv):
    if installing_cnv:
        yield
    else:
        with disable_default_sources_in_operatorhub(admin_client=admin_client):
            yield
