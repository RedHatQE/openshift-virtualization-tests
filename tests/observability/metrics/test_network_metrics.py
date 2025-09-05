import pytest

from tests.observability.metrics.constants import (
    KUBEVIRT_VMI_NETWORK_RECEIVE_PACKETS_TOTAL,
    KUBEVIRT_VMI_NETWORK_TRANSMIT_PACKETS_TOTAL,
)
from tests.observability.metrics.utils import (
    validate_network_traffic_metrics_value,
    validate_vmi_network_receive_and_transmit_packets_total,
)

RX_PACKETS_METRIC = {"metric_name": KUBEVIRT_VMI_NETWORK_RECEIVE_PACKETS_TOTAL, "packets_kind": "rx_packets"}
TX_PACKETS_METRIC = {"metric_name": KUBEVIRT_VMI_NETWORK_TRANSMIT_PACKETS_TOTAL, "packets_kind": "tx_packets"}


@pytest.mark.parametrize(
    "vm_for_test",
    [
        pytest.param(
            "network-metrics",
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("vm_for_test", "linux_vm_for_test_interface_name")
class TestVmiNetworkMetricsLinux:
    @pytest.mark.parametrize(
        "metric_dict",
        [
            pytest.param(
                RX_PACKETS_METRIC,
                marks=(pytest.mark.polarion("CNV-11176")),
            ),
            pytest.param(
                TX_PACKETS_METRIC,
                marks=(pytest.mark.polarion("CNV-11220")),
            ),
        ],
        indirect=False,
    )
    @pytest.mark.s390x
    def test_kubevirt_vmi_network_receive_and_transmit_packets_total(
        self, prometheus, metric_dict, vm_for_test, linux_vm_for_test_interface_name, generated_network_traffic
    ):
        validate_vmi_network_receive_and_transmit_packets_total(
            metric_dict=metric_dict,
            vm=vm_for_test,
            vm_interface_name=linux_vm_for_test_interface_name,
            prometheus=prometheus,
        )

    @pytest.mark.polarion("CNV-11177")
    @pytest.mark.s390x
    def test_kubevirt_vmi_network_traffic_bytes_total(
        self, prometheus, vm_for_test, linux_vm_for_test_interface_name, generated_network_traffic
    ):
        validate_network_traffic_metrics_value(
            prometheus=prometheus,
            vm=vm_for_test,
            interface_name=linux_vm_for_test_interface_name,
        )


@pytest.mark.tier3
class TestVmiNetworkMetricsWindows:
    @pytest.mark.parametrize(
        "metric_dict",
        [
            pytest.param(
                RX_PACKETS_METRIC,
                marks=(pytest.mark.polarion("CNV-11843")),
            ),
            pytest.param(
                TX_PACKETS_METRIC,
                marks=(pytest.mark.polarion("CNV-11844")),
            ),
        ],
    )
    def test_kubevirt_vmi_network_receive_and_transmit_packets_total_windows_vm(
        self,
        prometheus,
        windows_vm_for_test,
        windows_vm_for_test_interface_name,
        generated_network_traffic_windows_vm,
        metric_dict,
    ):
        validate_vmi_network_receive_and_transmit_packets_total(
            metric_dict=metric_dict,
            vm=windows_vm_for_test,
            vm_interface_name=windows_vm_for_test_interface_name,
            prometheus=prometheus,
        )

    @pytest.mark.polarion("CNV-11846")
    def test_kubevirt_vmi_network_traffic_bytes_total_windows_vm(
        self, prometheus, windows_vm_for_test, windows_vm_for_test_interface_name, generated_network_traffic_windows_vm
    ):
        validate_network_traffic_metrics_value(
            prometheus=prometheus,
            vm=windows_vm_for_test,
            interface_name=windows_vm_for_test_interface_name,
        )
