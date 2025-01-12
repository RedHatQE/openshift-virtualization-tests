import pytest

from tests.observability.constants import KUBEVIRT_STR_LOWER
from tests.observability.utils import validate_metrics_value
from utilities.constants import CRITICAL_STR
from utilities.monitoring import validate_alerts

KUBEVIRT_VIRT_OPERATOR_LEADING = "kubevirt_virt_operator_leading"
TEST_KUBEVIRT_VIRT_OPERATOR_LEADING = f"test_{KUBEVIRT_VIRT_OPERATOR_LEADING}"


@pytest.mark.usefixtures("annotated_virt_operator_endpoint")
class TestVirtOperatorLeading:
    @pytest.mark.dependency(name=TEST_KUBEVIRT_VIRT_OPERATOR_LEADING)
    @pytest.mark.polarion("CNV-10841")
    def test_kubevirt_virt_operator_leading(self, prometheus):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VIRT_OPERATOR_LEADING,
            expected_value="0",
        )

    @pytest.mark.dependency(depends=[TEST_KUBEVIRT_VIRT_OPERATOR_LEADING])
    @pytest.mark.parametrize(
        "alert_tested",
        [
            pytest.param(
                {
                    "alert_name": "NoLeadingVirtOperator",
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                },
                marks=(pytest.mark.polarion("CNV-8828")),
                id="Test_NoLeadingVirtOperator",
            )
        ],
        indirect=True,
    )
    def test_no_leading_virt_operator(self, prometheus, alert_tested):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )
