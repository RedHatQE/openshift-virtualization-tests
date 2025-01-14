import logging

import pytest

from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    HOSTPATH_PROVISIONER_OPERATOR,
    TIMEOUT_2MIN,
    WARNING_STR,
)
from utilities.monitoring import validate_alerts

pytestmark = [pytest.mark.usefixtures("skip_if_hpp_not_exist", "hpp_condition_available_scope_module")]

LOGGER = logging.getLogger(__name__)


class TestHPPCrReady:
    @pytest.mark.polarion("CNV-11022")
    def test_kubevirt_hpp_cr_ready_metric(self, prometheus, modified_hpp_non_exist_node_selector):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_hpp_cr_ready",
            expected_value="0",
        )


@pytest.mark.usefixtures("hpp_pod_sharing_pool_path")
class TestHPPSharingPoolPathWithOS:
    TEST_HPP_POOL_NAME = "test-hpp-pool-path"

    @pytest.mark.dependency(name=TEST_HPP_POOL_NAME)
    @pytest.mark.polarion("CNV-11221")
    def test_kubevirt_hpp_pool_path_shared_path_metric(self, prometheus):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_hpp_pool_path_shared_with_os",
            expected_value="1",
        )

    @pytest.mark.dependency(depends=[TEST_HPP_POOL_NAME])
    @pytest.mark.parametrize(
        "alert_tested",
        [
            pytest.param(
                {
                    "alert_name": "HPPSharingPoolPathWithOS",
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": HOSTPATH_PROVISIONER_OPERATOR,
                    },
                },
                marks=pytest.mark.polarion("CNV-11222"),
            ),
        ],
        indirect=True,
    )
    def test_hpp_sharing_pool_path_alert(self, prometheus, alert_tested):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
            timeout=TIMEOUT_2MIN,
        )


class TestHPPUpMetric:
    @pytest.mark.parametrize(
        "scaled_deployment",
        [pytest.param({"deployment_name": HOSTPATH_PROVISIONER_OPERATOR, "replicas": 0})],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-10435")
    def test_kubevirt_hpp_operator_up_metric(
        self,
        prometheus,
        disabled_virt_operator,
        scaled_deployment,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_hpp_operator_up",
            expected_value="0",
        )
