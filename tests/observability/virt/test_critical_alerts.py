import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.observability.constants import (
    CRITICAL_ALERTS_LIST,
    EXPECTED_METRICS_THRESHOLD,
    KUBEVIRT_STR_LOWER,
    VIRT_API_REST_ERRORS_BURST,
    VIRT_CONTROLLER_REST_ERRORS_BURST,
    VIRT_HANDLER_REST_ERRORS_BURST,
    VIRT_OPERATOR_REST_ERRORS_BURST,
)
from utilities.constants import (
    CRITICAL_STR,
    KUBEVIRT_HCO_NAME,
    TIMEOUT_4MIN,
    TIMEOUT_6MIN,
)
from utilities.monitoring import validate_alerts


@pytest.mark.parametrize(
    "modified_errors_burst_alerts_expression",
    [
        pytest.param({
            "alerts_list": CRITICAL_ALERTS_LIST,
            "threshold_for_rule_expression": str(EXPECTED_METRICS_THRESHOLD),
        })
    ],
    indirect=True,
)
@pytest.mark.usefixtures("modified_errors_burst_alerts_expression")
class TestCriticalAlerts:
    @pytest.mark.parametrize(
        "removed_cluster_role_binding, alert_tested",
        [
            pytest.param(
                "kubevirt-controller",
                {
                    "alert_name": VIRT_CONTROLLER_REST_ERRORS_BURST,
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "threshold_for_rule_expression": EXPECTED_METRICS_THRESHOLD,
                },
                marks=(pytest.mark.polarion("CNV-8829")),
                id=f"Test_{VIRT_CONTROLLER_REST_ERRORS_BURST}",
            ),
            pytest.param(
                "kubevirt-handler",
                {
                    "alert_name": VIRT_HANDLER_REST_ERRORS_BURST,
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "threshold_for_rule_expression": EXPECTED_METRICS_THRESHOLD,
                },
                marks=(pytest.mark.polarion("CNV-8831")),
                id=f"Test_{VIRT_HANDLER_REST_ERRORS_BURST}",
            ),
            pytest.param(
                "kubevirt-apiserver",
                {
                    "alert_name": VIRT_API_REST_ERRORS_BURST,
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "threshold_for_rule_expression": EXPECTED_METRICS_THRESHOLD,
                },
                marks=(pytest.mark.polarion("CNV-8832")),
                id=f"Test_{VIRT_API_REST_ERRORS_BURST}",
            ),
        ],
        indirect=True,
    )
    def test_rest_errors_burst(
        self,
        prometheus,
        alert_tested,
        removed_cluster_role_binding,
        virt_rest_errors_burst_precondition,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
            timeout=TIMEOUT_4MIN,
        )


@pytest.mark.parametrize(
    "modified_errors_burst_alerts_expression",
    [pytest.param({"alerts_list": [VIRT_OPERATOR_REST_ERRORS_BURST], "threshold_for_rule_expression": "0.1"})],
    indirect=True,
)
@pytest.mark.usefixtures("modified_errors_burst_alerts_expression")
class TestVirtOperatorAlerts:
    @pytest.mark.parametrize(
        "annotated_resource, alert_tested",
        [
            pytest.param(
                {
                    "annotations": {
                        "a": "b",
                    },
                    "resource_type": KubeVirt,
                    "name": KUBEVIRT_HCO_NAME,
                },
                {
                    "alert_name": VIRT_OPERATOR_REST_ERRORS_BURST,
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "threshold_for_rule_expression": "0.1",
                    "pre_condition_timeout": TIMEOUT_6MIN,
                    "check_alert_cleaned": True,
                },
                marks=(pytest.mark.polarion("CNV-8830")),
                id=f"Test_{VIRT_OPERATOR_REST_ERRORS_BURST}",
            ),
        ],
        indirect=True,
    )
    def test_virt_operator_rest_errors_burst(
        self,
        prometheus,
        alert_tested,
        removed_kubevirt_operator_cluster_role_binding,
        annotated_resource,
        virt_rest_errors_burst_precondition,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
            timeout=TIMEOUT_4MIN,
        )
