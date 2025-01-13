import logging

import pytest

from tests.observability.alerts.network.utils import (
    CNAO_NOT_READY,
)
from utilities.constants import (
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    WARNING_STR,
)
from utilities.monitoring import validate_alerts

LOGGER = logging.getLogger(__name__)


class TestCnaoNotReady:
    @pytest.mark.parametrize(
        "cnao_ready, alert_tested",
        [
            pytest.param(
                CNAO_NOT_READY,
                {
                    "alert_name": CNAO_NOT_READY,
                    "labels": {
                        "severity": WARNING_STR,
                        "operator_health_impact": WARNING_STR,
                        "kubernetes_operator_component": CLUSTER_NETWORK_ADDONS_OPERATOR,
                    },
                    "check_alert_cleaned": True,
                },
                marks=(pytest.mark.polarion("CNV-7274")),
            ),
        ],
        indirect=True,
    )
    def test_alert_cnao_not_ready(
        self,
        prometheus,
        alert_tested,
        cnao_ready,
        invalid_cnao_linux_bridge,
    ):
        validate_alerts(
            prometheus=prometheus,
            alert_dict=alert_tested,
        )
