import logging

import pytest
from ocp_resources.ssp import SSP
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.utils import (
    get_olm_namespace,
)
from utilities.constants import (
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    VIRT_OPERATOR,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import scale_deployment_replicas
from utilities.virt import get_all_virt_pods_with_running_status

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


@pytest.fixture(scope="session")
def olm_namespace():
    return get_olm_namespace()


@pytest.fixture(scope="class")
def disabled_olm_operator(olm_namespace):
    with scale_deployment_replicas(
        deployment_name="olm-operator",
        namespace=olm_namespace.name,
        replica_count=0,
    ):
        yield


@pytest.fixture(scope="class")
def disabled_virt_operator(admin_client, hco_namespace, disabled_olm_operator):
    virt_pods_with_running_status = get_all_virt_pods_with_running_status(
        dyn_client=admin_client, hco_namespace=hco_namespace
    )
    virt_pods_count_before_disabling_virt_operator = len(virt_pods_with_running_status.keys())
    with scale_deployment_replicas(
        deployment_name=VIRT_OPERATOR,
        namespace=hco_namespace.name,
        replica_count=0,
    ):
        yield

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=get_all_virt_pods_with_running_status,
        dyn_client=admin_client,
        hco_namespace=hco_namespace,
    )
    sample = None
    try:
        for sample in samples:
            if len(sample.keys()) == virt_pods_count_before_disabling_virt_operator:
                return True
    except TimeoutExpiredError:
        LOGGER.error(
            f"After restoring replicas for {VIRT_OPERATOR},"
            f"{virt_pods_with_running_status} virt pods were expected to be in running state."
            f"Here are available virt pods: {sample}"
        )
        raise
