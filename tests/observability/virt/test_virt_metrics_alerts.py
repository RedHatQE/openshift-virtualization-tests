import pytest

from tests.observability.constants import KUBEVIRT_STR_LOWER, KUBEVIRT_VIRT_OPERATOR_READY
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    PENDING_STR,
    TIMEOUT_5MIN,
    TIMEOUT_10MIN,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_OPERATOR,
    WARNING_STR,
)
from utilities.monitoring import validate_alerts


class TestVirtControllerReady:
    @pytest.mark.parametrize(
        "scaled_deployment",
        [
            pytest.param(
                {"deployment_name": VIRT_CONTROLLER, "replicas": 0},
                marks=pytest.mark.polarion("CNV-11613"),
            )
        ],
        indirect=True,
    )
    def test_metric_kubevirt_virt_controller_ready(self, prometheus, disabled_virt_operator, scaled_deployment):
        validate_metrics_value(prometheus=prometheus, metric_name="kubevirt_virt_controller_ready", expected_value="0")


@pytest.mark.usefixtures(
    "initial_virt_operator_replicas_reverted", "modified_virt_operator_httpget_from_hco_and_delete_virt_operator_pods"
)
class TestLowReadyVirtOperatorCount:
    @pytest.mark.dependency(name=f"test_metric_{KUBEVIRT_VIRT_OPERATOR_READY}")
    @pytest.mark.polarion("CNV-11386")
    def test_metric_kubevirt_virt_operator_ready(
        self,
        prometheus,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            expected_value="0",
            metric_name=KUBEVIRT_VIRT_OPERATOR_READY,
        )

    @pytest.mark.parametrize(
        "alert_tested_scope_class",
        [
            pytest.param(
                {
                    "alert_name": "LowReadyVirtOperatorsCount",
                    "timeout": TIMEOUT_5MIN,
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "state": PENDING_STR,
                    "check_alert_cleaned": True,
                },
                marks=(pytest.mark.polarion("CNV-11380")),
            )
        ],
        indirect=True,
    )
    @pytest.mark.dependency(depends=[f"test_metric_{KUBEVIRT_VIRT_OPERATOR_READY}"])
    def test_alert_low_virt_operator_count(
        self,
        prometheus,
        alert_tested_scope_class,
    ):
        validate_alerts(prometheus=prometheus, alert_dict=alert_tested_scope_class)


class TestVirtPodsDownMetrics:
    @pytest.mark.parametrize(
        "metric_name, scaled_deployment",
        [
            pytest.param(
                "kubevirt_virt_api_up",
                {"deployment_name": VIRT_API, "replicas": 0},
                marks=pytest.mark.polarion("CNV-11724"),
                id="Test_kubevirt_virt_api_up",
            ),
            pytest.param(
                "kubevirt_virt_controller_up",
                {"deployment_name": VIRT_CONTROLLER, "replicas": 0},
                marks=pytest.mark.polarion("CNV-11725"),
                id="Test_kubevirt_virt_controller_up",
            ),
            pytest.param(
                "kubevirt_virt_operator_up",
                {"deployment_name": VIRT_OPERATOR, "replicas": 0},
                marks=pytest.mark.polarion("CNV-11723"),
                id="Test_kubevirt_virt_operator_up",
            ),
        ],
        indirect=["scaled_deployment"],
    )
    def test_metrics_virt_pods_down(
        self,
        prometheus,
        metric_name,
        disabled_virt_operator,
        scaled_deployment,
    ):
        validate_metrics_value(prometheus=prometheus, metric_name=metric_name, expected_value="0")


@pytest.mark.usefixtures("disabled_virt_operator", "virt_handler_daemonset_with_bad_image", "deleted_virt_handler_pods")
class TestLowKvmCounts:
    @pytest.mark.dependency(name="test_metric_kubevirt_nodes_with_kvm")
    @pytest.mark.polarion("CNV-11708")
    def test_metric_kubevirt_nodes_with_kvm(self, prometheus):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_nodes_with_kvm",
            expected_value="0",
        )

    @pytest.mark.dependency(depends=["test_metric_kubevirt_nodes_with_kvm"])
    @pytest.mark.parametrize(
        "alert_tested",
        [
            pytest.param(
                {
                    "alert_name": "LowKVMNodesCount",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                },
                marks=(pytest.mark.polarion("CNV-11053")),
            )
        ],
    )
    def test_low_kvm_nodes_count(
        self,
        prometheus,
        alert_tested,
    ):
        validate_alerts(prometheus=prometheus, alert_dict=alert_tested)


class TestVirtHandlerDaemonSet:
    @pytest.mark.parametrize(
        "alert_tested",
        [
            pytest.param(
                {
                    "alert_name": "VirtHandlerDaemonSetRolloutFailing",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "state": PENDING_STR,
                    "check_alert_cleaned": True,
                },
                marks=pytest.mark.polarion("CNV-3814"),
            ),
        ],
        indirect=True,
    )
    def test_alert_virt_handler(
        self,
        prometheus,
        alert_tested,
        disabled_virt_operator,
        virt_handler_daemonset_with_bad_image,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
            timeout=TIMEOUT_10MIN,
        )
