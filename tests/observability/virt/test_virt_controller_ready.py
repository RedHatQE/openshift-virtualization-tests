import pytest

from tests.observability.utils import validate_metrics_value
from utilities.constants import VIRT_CONTROLLER


@pytest.mark.usefixtures("disabled_virt_operator")
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
    @pytest.mark.s390x
    def test_metric_kubevirt_virt_controller_ready(self, prometheus, scaled_deployment):
        validate_metrics_value(prometheus=prometheus, metric_name="kubevirt_virt_controller_ready", expected_value="0")
