import logging

import pytest

from utilities.hco import get_installed_hco_csv
from utilities.infra import scale_deployment_replicas

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def scaled_deployment_scope_class(request, hco_namespace):
    with scale_deployment_replicas(
        deployment_name=request.param["deployment_name"],
        replica_count=request.param["replicas"],
        namespace=hco_namespace.name,
    ):
        yield


@pytest.fixture()
def csv_scope_function(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_installed_hco_csv(admin_client=admin_client, hco_namespace=hco_namespace)
