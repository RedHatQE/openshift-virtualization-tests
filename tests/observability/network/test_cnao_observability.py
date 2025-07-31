import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_CNAO_KUBEMACPOOL_DUPLICATE_MACS,
    KUBEVIRT_CNAO_KUBEMACPOOL_MANAGER_UP,
    KUBEVIRT_CNAO_OPERATOR_UP,
)
from tests.observability.utils import validate_metrics_value
from utilities.constants import CLUSTER_NETWORK_ADDONS_OPERATOR, TIMEOUT_5MIN


class TestCnaoDown:
    @pytest.mark.polarion("CNV-11302")
    @pytest.mark.s390x
    def test_metric_kubevirt_cnao_operator_up(
        self, prometheus, disabled_virt_operator, wait_csv_image_updated_with_bad_image
    ):
        validate_metrics_value(
            prometheus=prometheus,
            expected_value="0",
            metric_name=KUBEVIRT_CNAO_OPERATOR_UP,
            timeout=TIMEOUT_5MIN,
        )


@pytest.mark.usefixtures(
    "duplicate_mac_vm1", "duplicate_mac_vm2", "updated_namespace_with_kmp", "restarted_kmp_controller"
)
class TestDuplicateMacs:
    @pytest.mark.polarion("CNV-11304")
    @pytest.mark.s390x
    def test_metric_kubevirt_cnao_kubemacpool_duplicate_macs(self, prometheus):
        validate_metrics_value(
            prometheus=prometheus,
            expected_value="1",
            metric_name=KUBEVIRT_CNAO_KUBEMACPOOL_DUPLICATE_MACS,
        )


@pytest.mark.usefixtures("updated_cnao_kubemacpool_with_bad_image_csv")
class TestKubeMacPool:
    @pytest.mark.polarion("CNV-11305")
    @pytest.mark.s390x
    def test_metric_kubevirt_cnao_kubemacpool_manager_up(self, prometheus):
        validate_metrics_value(
            prometheus=prometheus,
            expected_value="0",
            metric_name=KUBEVIRT_CNAO_KUBEMACPOOL_MANAGER_UP,
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
    @pytest.mark.s390x
    def test_metric_kubevirt_cnao_cr_kubemacpool_aggregated(self, prometheus, scaled_deployment):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_cnao_cr_kubemacpool_aggregated",
            expected_value="0",
        )
