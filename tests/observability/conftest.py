import logging

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.namespace import Namespace
from ocp_resources.prometheus_rule import PrometheusRule
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import (
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    VIRT_OPERATOR,
)
from utilities.hco import get_installed_hco_csv
from utilities.infra import get_deployment_by_name, scale_deployment_replicas
from utilities.monitoring import wait_for_firing_alert_clean_up
from utilities.virt import get_all_virt_pods_with_running_status

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def prometheus_k8s_rules_cnv(hco_namespace):
    return PrometheusRule(name="prometheus-k8s-rules-cnv", namespace=hco_namespace.name)


@pytest.fixture(scope="class")
def prometheus_existing_records(prometheus_k8s_rules_cnv):
    return [
        component["rules"]
        for component in prometheus_k8s_rules_cnv.instance.to_dict()["spec"]["groups"]
        if component["name"] == "runbook_url.rules"
    ][0]


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


def get_olm_namespace():
    olm_ns = Namespace(name="openshift-operator-lifecycle-manager")
    if olm_ns.exists:
        return olm_ns
    raise ResourceNotFoundError(f"Namespace: {olm_ns.name} not found.")
