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
    @pytest.mark.ipv6
    @pytest.mark.s390x
    def test_kubevirt_vmi_network_traffic_bytes_total(
        self,
        prometheus,
        vm_for_test,
        linux_vm_for_test_interface_name,
        generated_network_traffic,
        network_packet_received_linux_vm,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-29829 # <skip-jira-utils-check>
        Polarion: CNV-11177
        """
        validate_network_traffic_metrics_value(
            prometheus=prometheus,
            vm=vm_for_test,
            network_packet_received=network_packet_received_linux_vm,
        )


@pytest.mark.tier3
@pytest.mark.windows
class TestVmiNetworkMetricsWindows:
    def test_kubevirt_vmi_network_traffic_bytes_total_windows_vm(
        self,
        prometheus,
        windows_vm_for_test,
        windows_vm_for_test_interface_name,
        generated_network_traffic_windows_vm,
        network_packet_received_windows_vm,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-36659 # <skip-jira-utils-check>
        Polarion: CNV-11846
        """
        validate_network_traffic_metrics_value(
            prometheus=prometheus, vm=windows_vm_for_test, network_packet_received=network_packet_received_windows_vm
        )
