import pytest

from tests.observability.constants import KUBEVIRT_VIRT_OPERATOR_READY
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_OPERATOR,
)


class TestKubevirtVirtOperatorReady:
    @pytest.mark.polarion("CNV-11386")
    def test_metric_kubevirt_virt_operator_ready(
        self,
        prometheus,
        initial_virt_operator_replicas_reverted,
        modified_virt_operator_httpget_from_hco_and_delete_virt_operator_pods,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            expected_value="0",
            metric_name=KUBEVIRT_VIRT_OPERATOR_READY,
        )


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
