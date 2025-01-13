import pytest

from tests.observability.metrics.utils import (
    validate_network_traffic_metrics_value,
    validate_vmi_network_receive_and_transmit_packets_total,
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
    @pytest.mark.parametrize(
        "metric_dict",
        [
            pytest.param(
                {"metric_name": "kubevirt_vmi_network_receive_packets_total", "packets_kind": "rx_packets"},
                marks=(pytest.mark.polarion("CNV-11176")),
            ),
            pytest.param(
                {"metric_name": "kubevirt_vmi_network_transmit_packets_total", "packets_kind": "tx_packets"},
                marks=(pytest.mark.polarion("CNV-11220")),
            ),
        ],
        indirect=False,
    )
    def test_kubevirt_vmi_network_receive_and_transmit_packets_total(
        self, prometheus, metric_dict, vm_for_test, vm_for_test_interface_name, generated_network_traffic
    ):
        validate_vmi_network_receive_and_transmit_packets_total(
            metric_dict=metric_dict, vm=vm_for_test, vm_interface_name=vm_for_test_interface_name, prometheus=prometheus
        )

    @pytest.mark.polarion("CNV-11177")
    def test_kubevirt_vmi_network_traffic_bytes_total(
        self, prometheus, vm_for_test, vm_for_test_interface_name, generated_network_traffic
    ):
        validate_network_traffic_metrics_value(
            prometheus=prometheus,
            vm=vm_for_test,
            interface_name=vm_for_test_interface_name,
        )
