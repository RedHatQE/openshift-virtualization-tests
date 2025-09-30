import pytest

from tests.observability.metrics.utils import validate_network_traffic_metrics_value


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
    @pytest.mark.polarion("CNV-11846")
    def test_kubevirt_vmi_network_traffic_bytes_total_windows_vm(
        self, prometheus, windows_vm_for_test, windows_vm_for_test_interface_name, generated_network_traffic_windows_vm
    ):
        validate_network_traffic_metrics_value(
            prometheus=prometheus,
            vm=windows_vm_for_test,
            interface_name=windows_vm_for_test_interface_name,
        )
