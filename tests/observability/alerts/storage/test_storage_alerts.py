import pytest

from tests.observability.alerts.utils import CONTAINERIZED_DATA_IMPORTER
from tests.observability.utils import validate_metrics_value
from utilities.constants import CDI_OPERATOR, CRITICAL_STR, HOSTPATH_PROVISIONER_OPERATOR, NONE_STRING, WARNING_STR
from utilities.monitoring import validate_alerts


class TestCdiAlerts:
    @pytest.mark.parametrize(
        "alert_tested",
        [
            pytest.param(
                {
                    "alert_name": "CDIDataVolumeUnusualRestartCount",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": CONTAINERIZED_DATA_IMPORTER,
                    },
                    "check_alert_cleaned": True,
                },
                marks=(pytest.mark.polarion("CNV-10019")),
                id="Test_CDIDataVolumeUnusualRestartCount",
            )
        ],
        indirect=True,
    )
    def test_cdi_data_volume_unusual_restart_count(
        self,
        prometheus,
        alert_tested,
        created_fake_data_volume_resource,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )

    @pytest.mark.parametrize(
        "alert_tested",
        [
            pytest.param(
                {
                    "alert_name": "CDIStorageProfilesIncomplete",
                    "labels": {
                        "severity": "info",
                        "operator_health_impact": NONE_STRING,
                        "kubernetes_operator_component": CONTAINERIZED_DATA_IMPORTER,
                    },
                    "check_alert_cleaned": True,
                },
                marks=(pytest.mark.polarion("CNV-10017")),
                id="Test_CDIStorageProfilesIncomplete",
            )
        ],
        indirect=True,
    )
    def test_cdi_storage_profiles_incomplete(
        self,
        prometheus,
        alert_tested,
        created_fake_storage_class_resource,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )

    @pytest.mark.parametrize(
        "alert_tested, scaled_deployment",
        [
            pytest.param(
                {
                    "alert_name": "CDIOperatorDown",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": CONTAINERIZED_DATA_IMPORTER,
                    },
                    "check_alert_cleaned": True,
                },
                {"deployment_name": CDI_OPERATOR, "replicas": 0},
                marks=(pytest.mark.polarion("CNV-10018")),
                id="Test_CDIOperatorDown",
            ),
        ],
        indirect=True,
    )
    def test_cdi_operator_down(
        self,
        prometheus,
        alert_tested,
        disabled_virt_operator,
        scaled_deployment,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )


@pytest.mark.parametrize(
    "scaled_deployment_scope_class",
    [{"deployment_name": HOSTPATH_PROVISIONER_OPERATOR, "replicas": 0}],
    indirect=["scaled_deployment_scope_class"],
)
@pytest.mark.usefixtures("disabled_virt_operator", "scaled_deployment_scope_class")
class TestHPPAlertAndMetric:
    @pytest.mark.polarion("CNV-10435")
    def test_kubevirt_hpp_operator_up_metric(
        self,
        prometheus,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_hpp_operator_up",
            expected_value="0",
        )

    @pytest.mark.parametrize(
        "alert_tested",
        [
            pytest.param(
                {
                    "alert_name": "HPPOperatorDown",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": HOSTPATH_PROVISIONER_OPERATOR,
                    },
                },
                marks=(pytest.mark.polarion("CNV-10022")),
                id="Test_HPPOperatorDown",
            ),
        ],
        indirect=True,
    )
    def test_hpp_operator_down(
        self,
        prometheus,
        alert_tested,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )
