import pytest

from tests.observability.metrics.constants import KUBEVIRT_SSP_TEMPLATE_VALIDATOR_REJECTED_INCREASE
from tests.observability.utils import validate_metric_value_within_range, validate_metrics_value
from utilities.constants import SSP_OPERATOR, VIRT_TEMPLATE_VALIDATOR

KUBEVIRT_SSP_TEMPLATE_VALIDATOR_UP = "kubevirt_ssp_template_validator_up"
KUBEVIRT_SSP_OPERATOR_UP = "kubevirt_ssp_operator_up"
KUBEVIRT_SSP_OPERATOR_RECONCILE_SUCCEEDED_AGGREGATED = "kubevirt_ssp_operator_reconcile_succeeded_aggregated"
KUBEVIRT_SSP_COMMON_TEMPLATES_RESTORED_INCREASE = "kubevirt_ssp_common_templates_restored_increase"


class TestSSPMetrics:
    @pytest.mark.parametrize(
        "scaled_deployment, metric_name",
        [
            pytest.param(
                {"deployment_name": SSP_OPERATOR, "replicas": 0},
                KUBEVIRT_SSP_OPERATOR_UP,
                marks=pytest.mark.polarion("CNV-11307"),
            ),
            pytest.param(
                {"deployment_name": VIRT_TEMPLATE_VALIDATOR, "replicas": 0},
                KUBEVIRT_SSP_TEMPLATE_VALIDATOR_UP,
                marks=pytest.mark.polarion("CNV-11349"),
            ),
        ],
        indirect=["scaled_deployment"],
    )
    def test_metrics_kubevirt_ssp_operator_validator_up(
        self, prometheus, paused_ssp_operator, scaled_deployment, metric_name
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=metric_name,
            expected_value="0",
        )


class TestSSPTemplateMetrics:
    @pytest.mark.polarion("CNV-11357")
    def test_metric_kubevirt_ssp_operator_reconcile_succeeded_aggregated(
        self, prometheus, paused_ssp_operator, template_validator_finalizer, deleted_ssp_operator_pod
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_SSP_OPERATOR_RECONCILE_SUCCEEDED_AGGREGATED,
            expected_value="0",
        )

    @pytest.mark.polarion("CNV-11356")
    def test_metric_kubevirt_ssp_common_templates_restored_increase(self, prometheus, template_modified):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=KUBEVIRT_SSP_COMMON_TEMPLATES_RESTORED_INCREASE,
            expected_value=1,
        )


@pytest.mark.parametrize(
    "common_instance_type_param_dict",
    [
        pytest.param(
            {
                "name": "basic",
                "memory_requests": "10Mi",
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("instance_type_for_test_scope_class", "created_multiple_failed_vms")
class TestSSPTemplateValidatorRejected:
    @pytest.mark.polarion("CNV-11310")
    def test_metric_kubevirt_ssp_template_validator_rejected_increase(
        self,
        prometheus,
        high_rate_rejected_vms_metric,
    ):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=KUBEVIRT_SSP_TEMPLATE_VALIDATOR_REJECTED_INCREASE,
            expected_value=float(high_rate_rejected_vms_metric + 1),
        )
