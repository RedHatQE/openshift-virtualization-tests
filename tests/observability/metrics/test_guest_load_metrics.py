import pytest

from tests.observability.metrics.utils import validate_metric_value_greater_than_initial_value


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
