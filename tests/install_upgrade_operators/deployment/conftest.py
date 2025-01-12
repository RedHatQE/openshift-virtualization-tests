import pytest

from utilities.constants import HPP_POOL
from utilities.infra import get_deployment_by_name, get_deployments


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
