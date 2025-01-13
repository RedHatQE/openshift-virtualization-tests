import logging

import pytest

from tests.observability.storage.constants import HPP_NOT_READY
from tests.observability.utils import validate_metrics_value
from utilities.constants import (
    CRITICAL_STR,
    HOSTPATH_PROVISIONER_OPERATOR,
    TIMEOUT_2MIN,
    TIMEOUT_6MIN,
    WARNING_STR,
)
from utilities.monitoring import validate_alerts

pytestmark = [pytest.mark.usefixtures("skip_if_hpp_not_exist", "hpp_condition_available_scope_module")]

LOGGER = logging.getLogger(__name__)


class TestHPPCrReady:
    KUBEVIRT_HPP_CR_READY = "kubevirt_hpp_cr_ready"
    TEST_KUBEVIRT_HPP_CR_READY = f"test_{KUBEVIRT_HPP_CR_READY}"

    @pytest.mark.dependency(name=TEST_KUBEVIRT_HPP_CR_READY)
    @pytest.mark.polarion("CNV-11022")
    def test_kubevirt_hpp_cr_ready_metric(self, prometheus, modified_hpp_non_exist_node_selector):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=self.KUBEVIRT_HPP_CR_READY,
            expected_value="0",
        )

    @pytest.mark.dependency(depends=[TEST_KUBEVIRT_HPP_CR_READY])
    @pytest.mark.parametrize(
        "alert_dict",
        [
            pytest.param(
                {
                    "alert_name": HPP_NOT_READY,
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": CRITICAL_STR,
                        "kubernetes_operator_component": HOSTPATH_PROVISIONER_OPERATOR,
                    },
                },
                marks=pytest.mark.polarion("CNV-11023"),
            ),
        ],
    )
    def test_hpp_not_ready_alert(self, prometheus, modified_hpp_non_exist_node_selector, alert_dict):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_dict,
            timeout=TIMEOUT_6MIN,
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
