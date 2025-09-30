import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError

from tests.observability.metrics.constants import KUBEVIRT_SSP_TEMPLATE_VALIDATOR_REJECTED_INCREASE
from tests.observability.metrics.utils import (
    COUNT_THREE,
    validate_metric_value_with_round_down,
    validate_metric_value_within_range,
)
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    SSP_OPERATOR,
    VIRT_TEMPLATE_VALIDATOR,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.virt import VirtualMachineForTests

KUBEVIRT_SSP_OPERATOR_UP = "kubevirt_ssp_operator_up"
KUBEVIRT_SSP_TEMPLATE_VALIDATOR_UP = "kubevirt_ssp_template_validator_up"
KUBEVIRT_SSP_COMMON_TEMPLATES_RESTORED_INCREASE = "kubevirt_ssp_common_templates_restored_increase"
KUBEVIRT_SSP_OPERATOR_RECONCILE_SUCCEEDED_AGGREGATED = "kubevirt_ssp_operator_reconcile_succeeded_aggregated"


@pytest.fixture()
def template_modified(admin_client, base_templates):
    with ResourceEditorValidateHCOReconcile(
        patches={base_templates[0]: {"metadata": {"annotations": {"description": "New Description"}}}}
    ):
        yield


@pytest.fixture(scope="class")
def created_multiple_failed_vms(
    instance_type_for_test_scope_class,
    unprivileged_client,
    namespace,
    request,
):
    """
    This fixture is trying to create wrong VMs multiple times for getting alert triggered
    """
    with instance_type_for_test_scope_class as vm_instance_type:
        for _ in range(request.param["vm_count"]):
            with pytest.raises(UnprocessibleEntityError):
                with VirtualMachineForTests(
                    name="non-creatable-vm",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    vm_instance_type=vm_instance_type,
                    diskless_vm=True,
                    vm_validation_rule={
                        "name": "minimal-required-memory",
                        "path": "jsonpath::.spec.domain.resources.requests.memory",
                        "rule": "integer",
                        "message": "This VM requires more memory.",
                        "min": 1073741824,
                    },
                ) as vm:
                    return vm


class TestSSPTemplate:
    @pytest.mark.polarion("CNV-11356")
    @pytest.mark.s390x
    def test_metric_kubevirt_ssp_common_templates_restored_increase(self, prometheus, template_modified):
        validate_metric_value_within_range(
            prometheus=prometheus,
            metric_name=KUBEVIRT_SSP_COMMON_TEMPLATES_RESTORED_INCREASE,
            expected_value=1,
        )

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
    @pytest.mark.s390x
    def test_metrics_kubevirt_ssp_operator_validator_up(
        self, prometheus, paused_ssp_operator, scaled_deployment, metric_name
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=metric_name,
            expected_value="0",
        )

    @pytest.mark.polarion("CNV-11357")
    @pytest.mark.s390x
    def test_metric_kubevirt_ssp_operator_reconcile_succeeded_aggregated(
        self, prometheus, paused_ssp_operator, template_validator_finalizer, deleted_ssp_operator_pod
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_SSP_OPERATOR_RECONCILE_SUCCEEDED_AGGREGATED,
            expected_value="0",
        )


@pytest.mark.parametrize(
    "initiate_metric_value, common_instance_type_param_dict, created_multiple_failed_vms",
    [
        pytest.param(
            KUBEVIRT_SSP_TEMPLATE_VALIDATOR_REJECTED_INCREASE,
            {
                "name": "basic",
                "memory_requests": "10Mi",
            },
            {"vm_count": COUNT_THREE},
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("initiate_metric_value", "instance_type_for_test_scope_class", "created_multiple_failed_vms")
class TestSSPTemplateValidatorRejected:
    @pytest.mark.polarion("CNV-11310")
    @pytest.mark.s390x
    def test_metric_kubevirt_ssp_template_validator_rejected_increase(self, prometheus, initiate_metric_value):
        validate_metric_value_with_round_down(
            prometheus=prometheus,
            metric_name=KUBEVIRT_SSP_TEMPLATE_VALIDATOR_REJECTED_INCREASE,
            expected_value=round(float(initiate_metric_value) + COUNT_THREE),
        )
