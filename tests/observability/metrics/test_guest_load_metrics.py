import pytest

from tests.observability.metrics.utils import validate_metric_value_greater_than_initial_value


class TestVMIGuestLoad:
    # todo: when the pr for updating the fedora will be merged, adjust the test.
    @pytest.mark.polarion("CNV-12369")
    def test_kubevirt_vmi_guest_load_centos(
        self,
        prometheus,
        fedora_vm_with_stress_ng,
        qemu_guest_agent_version_updated_centos,
        stressed_vm_cpu_fedora,
        guest_load_os_matrix__function__,
    ):
        validate_metric_value_greater_than_initial_value(
            prometheus=prometheus,
            metric_name=f"{guest_load_os_matrix__function__}{{name='{fedora_vm_with_stress_ng.name}'}}",
            initial_value=0,
        )
