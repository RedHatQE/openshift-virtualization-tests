import pytest
from pytest_testconfig import config as py_config

import utilities.hco
from utilities.constants.hco import HCO_SUBSCRIPTION
from utilities.infra import get_subscription
from utilities.operator import disable_default_sources_in_operatorhub


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


@pytest.fixture(scope="module")
def disabled_default_sources_in_operatorhub_scope_module(admin_client, installing_cnv):
    if installing_cnv:
        yield
    else:
        with disable_default_sources_in_operatorhub(admin_client=admin_client):
            yield
