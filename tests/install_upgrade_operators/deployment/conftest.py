import pytest

from utilities.infra import get_deployment_by_name


@pytest.fixture()
def deployment_by_name(request, admin_client, hco_namespace):
    """
    Gets a deployment object by name.
    """
    deployment_name = request.param["deployment_name"]
    yield get_deployment_by_name(
        namespace_name=hco_namespace.name, deployment_name=deployment_name, admin_client=admin_client
    )
