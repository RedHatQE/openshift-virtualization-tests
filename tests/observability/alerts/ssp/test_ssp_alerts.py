import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.deployment import Deployment

from tests.observability.alerts.constants import (
    SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED,
    SSP_DOWN,
    SSP_FAILING_TO_RECONCILE,
    SSP_HIGH_RATE_REJECTED_VMS,
    SSP_TEMPLATE_VALIDATOR_DOWN,
)
from tests.observability.metrics.constants import KUBEVIRT_SSP_TEMPLATE_VALIDATOR_REJECTED_INCREASE
from tests.observability.metrics.utils import validate_metric_value_within_range
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    CRITICAL_STR,
    SSP_OPERATOR,
    VIRT_TEMPLATE_VALIDATOR,
    WARNING_STR,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import get_pod_by_name_prefix
from utilities.monitoring import validate_alerts
from utilities.ssp import verify_ssp_pod_is_running
from utilities.virt import VirtualMachineForTests

KUBEVIRT_SSP_OPERATOR_UP = "kubevirt_ssp_operator_up"
KUBEVIRT_SSP_TEMPLATE_VALIDATOR_UP = "kubevirt_ssp_template_validator_up"
KUBEVIRT_SSP_COMMON_TEMPLATES_RESTORED_INCREASE = "kubevirt_ssp_common_templates_restored_increase"
KUBEVIRT_SSP_OPERATOR_RECONCILE_SUCCEEDED_AGGREGATED = "kubevirt_ssp_operator_reconcile_succeeded_aggregated"


@pytest.fixture(scope="class")
def template_validator_finalizer(hco_namespace):
    deployment = Deployment(name=VIRT_TEMPLATE_VALIDATOR, namespace=hco_namespace.name)
    with ResourceEditorValidateHCOReconcile(
        patches={deployment: {"metadata": {"finalizers": ["ssp.kubernetes.io/temporary-finalizer"]}}}
    ):
        yield


@pytest.fixture(scope="class")
def deleted_ssp_operator_pod(admin_client, hco_namespace):
    get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=SSP_OPERATOR,
        namespace=hco_namespace.name,
    ).delete(wait=True)
    yield
    verify_ssp_pod_is_running(dyn_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="class")
def template_modified(admin_client, base_templates):
    with ResourceEditorValidateHCOReconcile(
        patches={base_templates[0]: {"metadata": {"annotations": {"description": "New Description"}}}}
    ):
        yield


@pytest.fixture(scope="class")
def high_rate_rejected_vms_metric(prometheus_existing_records):
    for rule in prometheus_existing_records:
        if rule.get("alert") == SSP_HIGH_RATE_REJECTED_VMS:
            return int(rule["expr"][-1])


@pytest.fixture(scope="class")
def created_multiple_failed_vms(
    instance_type_for_test_scope_class,
    unprivileged_client,
    namespace,
    high_rate_rejected_vms_metric,
):
    """
    This fixture is trying to create wrong VMs multiple times for getting alert triggered
    """
    with instance_type_for_test_scope_class as vm_instance_type:
        for _ in range(high_rate_rejected_vms_metric + 1):
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

    @pytest.mark.parametrize(
        "scaled_deployment, alert_tested, alert_not_firing",
        [
            pytest.param(
                {"deployment_name": VIRT_TEMPLATE_VALIDATOR, "replicas": 0},
                {
                    "alert_name": SSP_TEMPLATE_VALIDATOR_DOWN,
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": SSP_OPERATOR,
                    },
                },
                SSP_TEMPLATE_VALIDATOR_DOWN,
                marks=pytest.mark.polarion("CNV-7615"),
            ),
            pytest.param(
                {"deployment_name": SSP_OPERATOR, "replicas": 0},
                {
                    "alert_name": SSP_DOWN,
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": SSP_OPERATOR,
                    },
                    "check_alert_cleaned": True,
                },
                SSP_DOWN,
                marks=pytest.mark.polarion("CNV-7614"),
            ),
        ],
        indirect=True,
    )
    def test_alert_ssp_pods_down(
        self,
        prometheus,
        alert_tested,
        alert_not_firing,
        paused_ssp_operator,
        scaled_deployment,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )

    @pytest.mark.dependency(name=f"test_{SSP_FAILING_TO_RECONCILE}")
    @pytest.mark.order(
        after="tests/observability/test_healthy_cluster_no_alerts.py::test_no_ssp_alerts_on_healthy_cluster"
    )
    @pytest.mark.parametrize(
        "alert_not_firing,alert_tested",
        [
            pytest.param(
                SSP_FAILING_TO_RECONCILE,
                {
                    "alert_name": SSP_FAILING_TO_RECONCILE,
                    "labels": {
                        "severity": CRITICAL_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": SSP_OPERATOR,
                    },
                },
                marks=pytest.mark.polarion("CNV-7711"),
            ),
        ],
        indirect=True,
    )
    def test_alert_ssp_failing_to_reconcile(
        self,
        prometheus,
        alert_tested,
        alert_not_firing,
        paused_ssp_operator,
        template_validator_finalizer,
        deleted_ssp_operator_pod,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )

    @pytest.mark.dependency(depends=[f"test_{SSP_FAILING_TO_RECONCILE}"])
    @pytest.mark.polarion("CNV-11357")
    def test_metric_kubevirt_ssp_operator_reconcile_succeeded_aggregated(self, prometheus):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_SSP_OPERATOR_RECONCILE_SUCCEEDED_AGGREGATED,
            expected_value="0",
        )


class TestSSPAlerts:
    @pytest.mark.dependency(name=f"test_{SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED}")
    @pytest.mark.parametrize(
        "alert_not_firing, alert_tested",
        [
            pytest.param(
                SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED,
                {
                    "alert_name": SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED,
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": "none",
                        "kubernetes_operator_component": SSP_OPERATOR,
                    },
                },
                marks=pytest.mark.polarion("CNV-7616"),
            ),
        ],
        indirect=True,
    )
    def test_alert_template_modification_reverted(
        self,
        prometheus,
        alert_tested,
        alert_not_firing,
        template_modified,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )

    @pytest.mark.dependency(depends=[f"test_{SSP_COMMON_TEMPLATES_MODIFICATION_REVERTED}"])
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
    @pytest.mark.dependency(name=f"test_{SSP_HIGH_RATE_REJECTED_VMS}")
    @pytest.mark.parametrize(
        "alert_not_firing,alert_tested",
        [
            pytest.param(
                SSP_HIGH_RATE_REJECTED_VMS,
                {
                    "alert_name": SSP_HIGH_RATE_REJECTED_VMS,
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": SSP_OPERATOR,
                    },
                },
                marks=pytest.mark.polarion("CNV-7707"),
            ),
        ],
        indirect=True,
    )
    def test_alert_high_rate_rejected_vms(
        self,
        prometheus,
        alert_not_firing,
        alert_tested,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )

    @pytest.mark.dependency(depends=[f"test_{SSP_HIGH_RATE_REJECTED_VMS}"])
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
