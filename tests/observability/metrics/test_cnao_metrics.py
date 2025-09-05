import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_CNAO_CR_KUBEMACPOOL_DEPLOYED,
    KUBEVIRT_CNAO_CR_READY,
)
from tests.observability.utils import validate_metrics_value


class TestSSPMetrics:
    @pytest.mark.parametrize(
        "cluster_network_addons_operator_scaled_down_and_up, metric_name",
        [
            pytest.param(
                KUBEVIRT_CNAO_CR_READY,
                KUBEVIRT_CNAO_CR_READY,
                marks=pytest.mark.polarion("CNV-10514"),
            ),
            pytest.param(
                KUBEVIRT_CNAO_CR_KUBEMACPOOL_DEPLOYED,
                KUBEVIRT_CNAO_CR_KUBEMACPOOL_DEPLOYED,
                marks=pytest.mark.polarion("CNV-10538"),
            ),
        ],
        indirect=["cluster_network_addons_operator_scaled_down_and_up"],
    )
    @pytest.mark.s390x
    def test_kubevirt_cnao_cr_ready(
        self,
        prometheus,
        cluster_network_addons_operator_scaled_down_and_up,
        metric_name,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            expected_value="1",
            metric_name=metric_name,
        )
