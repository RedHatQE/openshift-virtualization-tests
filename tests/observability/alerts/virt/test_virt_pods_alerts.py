"""
Firing alerts for kubevirt pods
"""

import pytest

from tests.observability.constants import KUBEVIRT_STR_LOWER
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    CRITICAL_STR,
    PENDING_STR,
    TIMEOUT_10MIN,
    TIMEOUT_12MIN,
    TIMEOUT_15MIN,
    WARNING_STR,
)
from utilities.monitoring import validate_alerts


class TestVirtAlerts:
    @pytest.mark.parametrize(
        "scaled_deployment, alert_tested",
        [
            pytest.param(
                {"deployment_name": "virt-api", "replicas": 0},
                {
                    "alert_name": "VirtAPIDown",
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "check_alert_cleaned": True,
                },
                marks=pytest.mark.polarion("CNV-3603"),
                id="Test_VirtApiDown",
            ),
            pytest.param(
                {"deployment_name": "virt-controller", "replicas": 0},
                {
                    "alert_name": "VirtControllerDown",
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "check_alert_cleaned": True,
                },
                marks=pytest.mark.polarion("CNV-3604"),
            ),
            pytest.param(
                {"deployment_name": "virt-operator", "replicas": 0},
                {
                    "alert_name": "VirtOperatorDown",
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                },
                marks=pytest.mark.polarion("CNV-7482"),
            ),
        ],
        indirect=True,
    )
    def test_alert_virt_pods_down(
        self,
        prometheus,
        alert_tested,
        disabled_virt_operator,
        scaled_deployment,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
            timeout=TIMEOUT_15MIN,
        )

    @pytest.mark.parametrize(
        "scaled_deployment, alert_tested",
        [
            pytest.param(
                {"deployment_name": "virt-api", "replicas": 1},
                {
                    "alert_name": "LowVirtAPICount",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "state": PENDING_STR,
                },
                marks=pytest.mark.polarion("CNV-7601"),
            ),
            pytest.param(
                {"deployment_name": "virt-controller", "replicas": 1},
                {
                    "alert_name": "LowVirtControllersCount",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "timeout": TIMEOUT_12MIN,
                    "check_alert_cleaned": True,
                },
                marks=pytest.mark.polarion("CNV-7600"),
            ),
            pytest.param(
                # replicas for virt-operator should be 0, otherwise it will restore all pods
                {"deployment_name": "virt-operator", "replicas": 0},
                {
                    "alert_name": "LowVirtOperatorCount",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "state": PENDING_STR,
                },
                marks=pytest.mark.polarion("CNV-7599"),
            ),
        ],
        indirect=True,
    )
    def test_alert_virt_pods_low_count(
        self,
        prometheus,
        alert_tested,
        skip_when_one_node,
        disabled_olm_operator,
        disabled_virt_operator,
        scaled_deployment,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
            timeout=TIMEOUT_10MIN,
        )

    @pytest.mark.polarion("CNV-3814")
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
