import pytest

from tests.observability.alerts.constants import KUBEVIRT_VIRT_OPERATOR_READY
from tests.observability.constants import KUBEVIRT_STR_LOWER
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    COUNT_TWELVE,
    NONE_STRING,
    PENDING_STR,
    TIMEOUT_5MIN,
    TIMEOUT_15MIN,
    TIMEOUT_20MIN,
    WARNING_STR,
)
from utilities.monitoring import validate_alerts

VIRT_CONTROLLER_REST_ERRORS_HIGH = "VirtControllerRESTErrorsHigh"

pytestmark = pytest.mark.usefixtures("initial_virt_operator_replicas")


class TestRestErrorsHigh:
    @pytest.mark.parametrize(
        "removed_cluster_role_binding,alert_tested",
        [
            pytest.param(
                "kubevirt-controller",
                {
                    "alert_name": VIRT_CONTROLLER_REST_ERRORS_HIGH,
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                    "timeout": TIMEOUT_20MIN,
                },
                id=f"Test_{VIRT_CONTROLLER_REST_ERRORS_HIGH}",
            ),
            pytest.param(
                "kubevirt-handler",
                {
                    "alert_name": "VirtHandlerRESTErrorsHigh",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                },
                marks=(pytest.mark.polarion("CNV-9996")),
                id="Test_VirtHandlerRESTErrorsHigh",
            ),
            pytest.param(
                "kubevirt-apiserver",
                {
                    "alert_name": "VirtApiRESTErrorsHigh",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                },
                marks=(pytest.mark.polarion("CNV-9997")),
                id="Test_VirtApiRESTErrorsHigh",
            ),
        ],
        indirect=True,
    )
    def test_rest_errors_high(
        self,
        prometheus,
        removed_cluster_role_binding,
        alert_tested,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
            timeout=TIMEOUT_15MIN,
        )


class TestMigrationAlert:
    @pytest.mark.parametrize(
        "alert_tested, vm_for_migration_test, migrated_vm_multiple_times",
        [
            pytest.param(
                {
                    "alert_name": "KubeVirtVMIExcessiveMigrations",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": NONE_STRING,
                        "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    },
                },
                "vm-migrate",
                COUNT_TWELVE,
                marks=pytest.mark.polarion("CNV-10441"),
                id="Test_KubeVirtVMIExcessiveMigrations",
            ),
        ],
        indirect=True,
    )
    def test_kubevirt_vmi_excessive_migrations(
        self,
        prometheus,
        vm_for_migration_test,
        migrated_vm_multiple_times,
        alert_tested,
    ):
        alert_tested["labels"]["namespace"] = vm_for_migration_test.namespace
        validate_alerts(prometheus=prometheus, alert_dict=alert_tested)


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
