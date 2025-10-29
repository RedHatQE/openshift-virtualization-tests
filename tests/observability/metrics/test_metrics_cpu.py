import pytest

from tests.observability.metrics.utils import (
    ONE_CPU_CORES,
    ZERO_CPU_CORES,
    validate_metric_value_greater_than_initial_value,
    wait_for_metric_vmi_request_cpu_cores_output,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.mark.usefixtures("initial_metric_cpu_value_zero")
class TestMetricsCpu:
    @pytest.mark.polarion("CNV-9649")
    @pytest.mark.s390x
    def test_verify_metrics_vmi_request_cpu_sum(self, prometheus, running_metric_vm):
        wait_for_metric_vmi_request_cpu_cores_output(prometheus=prometheus, expected_cpu=ONE_CPU_CORES)

    @pytest.mark.polarion("CNV-9653")
    @pytest.mark.order(after="test_verify_metrics_vmi_request_cpu_sum")
    @pytest.mark.s390x
    def test_verify_metrics_stopped_vm(self, prometheus, stopped_metrics_vm):
        wait_for_metric_vmi_request_cpu_cores_output(prometheus=prometheus, expected_cpu=ZERO_CPU_CORES)

    @pytest.mark.polarion("CNV-9652")
    @pytest.mark.order(after="test_verify_metrics_stopped_vm")
    @pytest.mark.s390x
    def test_verify_metrics_paused_vm(
        self,
        prometheus,
        starting_metrics_vm,
        paused_metrics_vm,
    ):
        wait_for_metric_vmi_request_cpu_cores_output(prometheus=prometheus, expected_cpu=ONE_CPU_CORES)


@pytest.mark.usefixtures("initial_metric_cpu_value_zero")
class TestMetricsCpuErrorState:
    @pytest.mark.polarion("CNV-9654")
    @pytest.mark.s390x
    def test_verify_metrics_error_state_vm(self, prometheus, error_state_vm):
        wait_for_metric_vmi_request_cpu_cores_output(prometheus=prometheus, expected_cpu=ZERO_CPU_CORES)


class TestVMIGuestLoad:
    @pytest.mark.polarion("CNV-12369")
    def test_kubevirt_vmi_guest_load_centos(
        self,
        prometheus,
        centos_stream_10_vm,
        qemu_guest_agent_version_updated_centos,
        stressed_vm_cpu_centos,
        guest_load_os_matrix__function__,
    ):
        validate_metric_value_greater_than_initial_value(
            prometheus=prometheus,
            metric_name=f"{guest_load_os_matrix__function__}{{name='{centos_stream_10_vm.name}'}}",
            initial_value=0,
        )
