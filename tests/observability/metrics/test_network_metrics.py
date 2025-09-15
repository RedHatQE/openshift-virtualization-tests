import pytest

from tests.observability.metrics.utils import (
    validate_network_traffic_metrics_value,
)


@pytest.mark.parametrize(
    "vm_for_test",
    [
        pytest.param(
            "network-metrics",
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("vm_for_test", "vm_for_test_interface_name")
class TestVmiNetworkMetrics:
    @pytest.mark.polarion("CNV-11177")
    def test_kubevirt_vmi_network_traffic_bytes_total(
        self, prometheus, vm_for_test, vm_for_test_interface_name, generated_network_traffic
    ):
        validate_network_traffic_metrics_value(
            prometheus=prometheus,
            vm=vm_for_test,
            interface_name=vm_for_test_interface_name,
        )
