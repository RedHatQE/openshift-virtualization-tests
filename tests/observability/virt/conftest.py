import logging

import pytest
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.prometheus_rule import PrometheusRule
from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.alerts.virt.utils import (
    wait_kubevirt_operator_role_binding_resource,
)
from tests.observability.utils import get_kubevirt_operator_role_binding_resource
from utilities.constants import TIMEOUT_5MIN, TIMEOUT_10SEC
from utilities.monitoring import get_metrics_value

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def modified_errors_burst_alerts_expression(request, hco_namespace):
    rest_errors_burst_alerts_prometheus_rules = PrometheusRule(
        namespace=hco_namespace.name,
        name="prometheus-kubevirt-rules",
    )
    alert_names_and_expressions = {}
    alerts_prometheus_rules_dict = rest_errors_burst_alerts_prometheus_rules.instance.to_dict()
    for group in alerts_prometheus_rules_dict.get("spec").get("groups"):
        if group.get("name") == "alerts.rules":
            for alert_rule in group.get("rules"):
                alert_name = alert_rule.get("alert")
                if alert_name in request.param["alerts_list"]:
                    alert_rule.update({
                        "expr": (
                            alert_rule["expr"]
                            .replace("0.8", request.param["threshold_for_rule_expression"])  # Update threshold
                            .replace("[5m]", "[1m]")  # Update duration
                        ),
                        "for": "2m",  # Update the 'for' field
                    })
                    alert_names_and_expressions[alert_name] = alert_rule["expr"].split(">=")[0].strip()
    with ResourceEditor(patches={rest_errors_burst_alerts_prometheus_rules: alerts_prometheus_rules_dict}):
        yield alert_names_and_expressions


@pytest.fixture()
def virt_rest_errors_burst_precondition(
    prometheus,
    alert_tested,
    modified_errors_burst_alerts_expression,
):
    threshold = float(alert_tested["threshold_for_rule_expression"])
    query = modified_errors_burst_alerts_expression[alert_tested["alert_name"]]
    samples = TimeoutSampler(
        wait_timeout=alert_tested.get("pre_condition_timeout", TIMEOUT_5MIN),
        sleep=TIMEOUT_10SEC,
        prometheus=prometheus,
        func=get_metrics_value,
        metrics_name=query,
    )
    sample = None
    try:
        for sample in samples:
            if float(sample) >= threshold:
                return
    except TimeoutExpiredError:
        pytest.fail(
            f"Prometheus query: {query} output is returning non-expected results\n"
            f"Expected results: >= {threshold} for {TIMEOUT_5MIN} seconds\n"
            f"Actual results: {sample}"
        )


@pytest.fixture()
def annotated_resource(request, hco_namespace):
    resource = request.param["resource_type"](
        name=request.param["name"],
        namespace=hco_namespace.name,
    )

    with ResourceEditor(patches={resource: {"metadata": {"annotations": request.param["annotations"]}}}):
        yield


@pytest.fixture()
def kubevirt_operator_cluster_role_binding(admin_client):
    return get_kubevirt_operator_role_binding_resource(admin_client=admin_client)


@pytest.fixture()
def removed_kubevirt_operator_cluster_role_binding(admin_client, kubevirt_operator_cluster_role_binding):
    labels = kubevirt_operator_cluster_role_binding.instance.metadata.labels
    subjects = kubevirt_operator_cluster_role_binding.instance.to_dict()["subjects"]
    crb_object = ClusterRoleBinding(
        name=kubevirt_operator_cluster_role_binding.name,
        cluster_role=kubevirt_operator_cluster_role_binding.name,
        subjects=subjects,
    )
    if kubevirt_operator_cluster_role_binding.exists:
        kubevirt_operator_cluster_role_binding.clean_up()
    yield
    crb_object.deploy(wait=True)
    ResourceEditor({crb_object: {"metadata": {"labels": labels}}}).update()
    wait_kubevirt_operator_role_binding_resource(admin_client=admin_client)
