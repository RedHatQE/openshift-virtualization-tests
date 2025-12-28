import pytest

from utilities.constants import HPP_POOL, KUBEVIRT_MIGRATION_CONTROLLER
from utilities.infra import get_deployment_by_name, get_deployments
from utilities.jira import is_jira_open


@pytest.fixture()
def deployment_by_name(request, admin_client, hco_namespace):
    """
    Gets a deployment object by name.
    """
    deployment_name = request.param["deployment_name"]
    yield get_deployment_by_name(namespace_name=hco_namespace.name, deployment_name=deployment_name)


@pytest.fixture(scope="module")
def cnv_deployments_excluding_hpp_pool(admin_client, hco_namespace):
    return [
        deployment
        for deployment in get_deployments(admin_client=admin_client, namespace=hco_namespace.name)
        if not deployment.name.startswith(HPP_POOL)
    ]


@pytest.fixture()
def xfail_if_jira_75721_open(cnv_deployment_by_name):
    if cnv_deployment_by_name.name == KUBEVIRT_MIGRATION_CONTROLLER and is_jira_open(jira_id="CNV-75721"):
        pytest.xfail(f"{KUBEVIRT_MIGRATION_CONTROLLER} deployment is not running due to CNV-75721 bug")
