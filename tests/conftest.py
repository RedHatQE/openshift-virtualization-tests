import pytest
from pytest_testconfig import config as py_config
from ocp_utilities.infra import get_client
from utilities.infra import get_namespace, get_cnv_installed_csv


@pytest.fixture(scope="session")
def admin_client():
    """
    Get DynamicClient
    """
    return get_client()


@pytest.fixture(scope="session")
def openshift_cnv_namespace():
    return get_namespace(name=py_config["cnv_namespace"])


@pytest.fixture(scope="session")
def openshift_cnv_csv_scope_session(openshift_cnv_namespace):
    return get_cnv_installed_csv(
        namespace=openshift_cnv_namespace.name,
        subscription_name=py_config["hco_subscription"],
    )
