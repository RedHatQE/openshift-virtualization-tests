import pytest

from tests.observability.alerts.network.utils import CNAO_DOWN, KUBEMACPOOL_DOWN
from tests.observability.metrics.constants import (
    KUBEVIRT_CNAO_KUBEMACPOOL_DUPLICATE_MACS,
    KUBEVIRT_CNAO_KUBEMACPOOL_MANAGER_UP,
    KUBEVIRT_CNAO_OPERATOR_UP,
)
from tests.observability.utils import validate_metrics_value
from utilities.constants import CLUSTER_NETWORK_ADDONS_OPERATOR, CRITICAL_STR, TIMEOUT_5MIN, WARNING_STR
from utilities.monitoring import validate_alerts


@pytest.mark.parametrize(
    "cnao_ready",
    [
        pytest.param(
            CNAO_DOWN,
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures("cnao_ready", "disabled_virt_operator", "invalid_cnao_operator")
class TestCnaoDown:
    @pytest.mark.dependency(name=f"test_{KUBEVIRT_CNAO_OPERATOR_UP}")
    @pytest.mark.polarion("CNV-11302")
    def test_metric_kubevirt_cnao_operator_up(self, prometheus):
        validate_metrics_value(
            prometheus=prometheus,
            expected_value="0",
            metric_name=KUBEVIRT_CNAO_OPERATOR_UP,
            timeout=TIMEOUT_5MIN,
        )

    @pytest.mark.dependency(depends=[f"test_{KUBEVIRT_CNAO_OPERATOR_UP}"])
    @pytest.mark.parametrize(
        "alert_tested",
        [
            pytest.param(
                {
                    "alert_name": CNAO_DOWN,
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": CLUSTER_NETWORK_ADDONS_OPERATOR,
                    },
                },
                marks=(pytest.mark.polarion("CNV-7275")),
            ),
        ],
        indirect=True,
    )
    def test_cnao_is_down(self, prometheus, alert_tested):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )


@pytest.mark.usefixtures(
    "duplicate_mac_vm1", "duplicate_mac_vm2", "updated_namespace_with_kmp", "restarted_kmp_controller"
)
class TestDuplicateMacs:
    @pytest.mark.dependency(name=f"test_{KUBEVIRT_CNAO_KUBEMACPOOL_DUPLICATE_MACS}")
    @pytest.mark.polarion("CNV-11304")
    def test_metric_kubevirt_cnao_kubemacpool_duplicate_macs(self, prometheus):
        validate_metrics_value(
            prometheus=prometheus,
            expected_value="1",
            metric_name=KUBEVIRT_CNAO_KUBEMACPOOL_DUPLICATE_MACS,
        )

    @pytest.mark.dependency(depends=[f"test_{KUBEVIRT_CNAO_KUBEMACPOOL_DUPLICATE_MACS}"])
    @pytest.mark.parametrize(
        "alert_tested",
        [
            pytest.param(
                {
                    "alert_name": "KubeMacPoolDuplicateMacsFound",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": CLUSTER_NETWORK_ADDONS_OPERATOR,
                    },
                },
                marks=(pytest.mark.polarion("CNV-7684")),
            ),
        ],
        indirect=True,
    )
    def test_duplicate_mac_alert(
        self,
        prometheus,
        alert_tested,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )


@pytest.mark.parametrize(
    "alert_not_firing",
    [
        pytest.param(
            KUBEMACPOOL_DOWN,
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures("alert_not_firing", "updated_cnao_kubemacpool_with_bad_image_csv")
class TestKubeMacPool:
    @pytest.mark.dependency(name=f"test_{KUBEVIRT_CNAO_KUBEMACPOOL_MANAGER_UP}")
    @pytest.mark.polarion("CNV-11305")
    def test_metric_kubevirt_cnao_kubemacpool_manager_up(self, prometheus):
        validate_metrics_value(
            prometheus=prometheus,
            expected_value="0",
            metric_name=KUBEVIRT_CNAO_KUBEMACPOOL_MANAGER_UP,
        )

    @pytest.mark.dependency(depends=[f"test_{KUBEVIRT_CNAO_KUBEMACPOOL_MANAGER_UP}"])
    @pytest.mark.parametrize(
        "alert_tested",
        [
            pytest.param(
                {
                    "alert_name": KUBEMACPOOL_DOWN,
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": CLUSTER_NETWORK_ADDONS_OPERATOR,
                    },
                },
                marks=(pytest.mark.polarion("CNV-8820")),
            ),
        ],
        indirect=True,
    )
    def test_alert_kubemacpooldown(
        self,
        prometheus,
        alert_tested,
        updated_cnao_kubemacpool_with_bad_image_csv,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )

    @pytest.mark.parametrize(
        "scaled_deployment",
        [
            pytest.param(
                {"deployment_name": CLUSTER_NETWORK_ADDONS_OPERATOR, "replicas": 0},
                marks=pytest.mark.polarion("CNV-11627"),
            )
        ],
        indirect=True,
    )
    def test_metric_kubevirt_cnao_cr_kubemacpool_aggregated(self, prometheus, scaled_deployment):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_cnao_cr_kubemacpool_aggregated",
            expected_value="0",
        )
