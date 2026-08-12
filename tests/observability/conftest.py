import logging

import pytest
from ocp_resources.ssp import SSP

from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import scale_deployment_replicas

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def paused_ssp_operator(admin_client, hco_namespace, ssp_resource_scope_class):
    """
    Pause ssp-operator to avoid from reconciling any related objects
    """
    with ResourceEditorValidateHCOReconcile(
        admin_client=admin_client,
        patches={ssp_resource_scope_class: {"metadata": {"annotations": {"kubevirt.io/operator.paused": "true"}}}},
        list_resource_reconcile=[SSP],
    ):
        yield


@pytest.fixture()
def scaled_deployment(request, hco_namespace, admin_client):
    with scale_deployment_replicas(
        deployment_name=request.param["deployment_name"],
        replica_count=request.param["replicas"],
        namespace=hco_namespace.name,
        client=admin_client,
    ):
        yield
