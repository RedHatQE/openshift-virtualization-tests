import logging

import pytest
from ocp_resources.ssp import SSP

from utilities.hco import ResourceEditorValidateHCOReconcile

LOGGER = logging.getLogger(__name__)
ANNOTATIONS_FOR_VIRT_OPERATOR_ENDPOINT = {
    "annotations": {
        "control-plane.alpha.kubernetes.io/leader": '{"holderIdentity":"fake-holder",'
        '"leaseDurationSeconds":3600,"acquireTime":"now()",'
        '"renewTime":"now()+1","leaderTransitions":1}'
    }
}


@pytest.fixture(scope="class")
def paused_ssp_operator(admin_client, hco_namespace, ssp_resource_scope_class):
    """
    Pause ssp-operator to avoid from reconciling any related objects
    """
    with ResourceEditorValidateHCOReconcile(
        patches={ssp_resource_scope_class: {"metadata": {"annotations": {"kubevirt.io/operator.paused": "true"}}}},
        list_resource_reconcile=[SSP],
    ):
        yield
