import logging

import pytest
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.endpoints import Endpoints
from ocp_resources.prometheus_rule import PrometheusRule
from ocp_resources.resource import ResourceEditor
from ocp_resources.ssp import SSP
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.alerts.network.utils import wait_for_cnao_pod_running
from tests.observability.alerts.utils import get_olm_namespace
from tests.observability.alerts.virt.utils import (
    get_number_of_virt_pods,
    wait_for_all_virt_pods_running,
    wait_for_role_binding_resource,
)
from tests.observability.constants import CRITICAL_ALERTS_LIST, ROLE_BINDING_LIST
from tests.observability.metrics.utils import validate_initial_virt_operator_replicas_reverted
from utilities.constants import (
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    VIRT_OPERATOR,
)
from utilities.hco import ResourceEditorValidateHCOReconcile, get_installed_hco_csv
from utilities.infra import get_deployment_by_name, get_pod_by_name_prefix, scale_deployment_replicas
from utilities.monitoring import wait_for_firing_alert_clean_up
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


@pytest.fixture(scope="class")
def prometheus_k8s_rules_cnv(hco_namespace):
    return PrometheusRule(name="prometheus-k8s-rules-cnv", namespace=hco_namespace.name)


@pytest.fixture(scope="class")
def prometheus_existing_records(prometheus_k8s_rules_cnv):
    return [
        component["rules"]
        for component in prometheus_k8s_rules_cnv.instance.to_dict()["spec"]["groups"]
        if component["name"] == "alerts.rules"
    ][0]


@pytest.fixture(scope="class")
def annotated_virt_operator_endpoint(hco_namespace, prometheus):
    virt_operator_endpoint = Endpoints(
        name=VIRT_OPERATOR,
        namespace=hco_namespace.name,
    )
    with ResourceEditor(patches={virt_operator_endpoint: {"metadata": ANNOTATIONS_FOR_VIRT_OPERATOR_ENDPOINT}}):
        yield
    wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name="NoLeadingVirtOperator")


@pytest.fixture()
def alert_tested(prometheus, request):
    alert_dict = request.param
    yield alert_dict
    if alert_dict.get("check_alert_cleaned"):
        wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=alert_dict["alert_name"])


@pytest.fixture(scope="class")
def alert_tested_scope_class(prometheus, request):
    alert_dict = request.param
    yield alert_dict
    if alert_dict.get("check_alert_cleaned"):
        wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=alert_dict["alert_name"])


@pytest.fixture(scope="class")
def cnao_ready(request, admin_client, hco_namespace, prometheus):
    yield
    get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=CLUSTER_NETWORK_ADDONS_OPERATOR,
        namespace=hco_namespace.name,
    ).delete(wait=True)
    wait_for_cnao_pod_running(admin_client=admin_client, hco_namespace=hco_namespace.name)
    wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=request.param)


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


@pytest.fixture(scope="class")
def csv_scope_class(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_installed_hco_csv(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="module")
def virt_operator_deployment(hco_namespace):
    return get_deployment_by_name(deployment_name=VIRT_OPERATOR, namespace_name=hco_namespace.name)


@pytest.fixture(scope="module")
def initial_virt_operator_replicas(prometheus, virt_operator_deployment, hco_namespace):
    virt_operator_deployment_initial_replicas = str(virt_operator_deployment.instance.status.replicas)
    assert virt_operator_deployment_initial_replicas, f"Not replicas found for {VIRT_OPERATOR}"
    return virt_operator_deployment_initial_replicas


@pytest.fixture(scope="class")
def initial_virt_operator_replicas_reverted(prometheus, initial_virt_operator_replicas):
    validate_initial_virt_operator_replicas_reverted(
        prometheus=prometheus, initial_virt_operator_replicas=initial_virt_operator_replicas
    )


@pytest.fixture()
def removed_cluster_role_binding(request, disabled_virt_operator_and_reconcile_role_binding):
    name = request.param
    binding_role = ClusterRoleBinding(
        name=name,
        cluster_role=name,
    )
    binding_role.clean_up()
    yield


@pytest.fixture(scope="class")
def disabled_virt_operator_and_reconcile_role_binding(
    admin_client,
    prometheus,
    hco_namespace,
    disabled_olm_operator,
):
    number_of_virt_pods = get_number_of_virt_pods(admin_client=admin_client, hco_namespace=hco_namespace)

    with scale_deployment_replicas(
        deployment_name=VIRT_OPERATOR,
        namespace=hco_namespace.name,
        replica_count=0,
    ):
        yield

    wait_for_all_virt_pods_running(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        number_of_virt_pods=number_of_virt_pods,
    )

    for role in ROLE_BINDING_LIST:
        wait_for_role_binding_resource(
            admin_client=admin_client,
            cluster_role_binding=role,
        )

    for alert in CRITICAL_ALERTS_LIST:
        wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=alert)
