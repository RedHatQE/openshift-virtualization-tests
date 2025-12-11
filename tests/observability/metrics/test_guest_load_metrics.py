import pytest

from tests.observability.metrics.utils import validate_metric_value_greater_than_initial_value

KUBEVIRT_VMI_GUEST_LOAD_METRIC = "kubevirt_vmi_guest_load"
GUEST_LOAD_TIME_PERIODS = [
    f"{KUBEVIRT_VMI_GUEST_LOAD_METRIC}_1m",
    f"{KUBEVIRT_VMI_GUEST_LOAD_METRIC}_5m",
    f"{KUBEVIRT_VMI_GUEST_LOAD_METRIC}_15m",
]


class TestVMIGuestLoad:
    # TODO: when the pr for updating the fedora will be merged, adjust the test.
    @pytest.mark.polarion("CNV-12369")
    def test_kubevirt_vmi_guest_load(
        self,
        prometheus,
        fedora_vm_with_stress_ng,
        qemu_guest_agent_version_validated,
        stressed_vm_cpu_fedora,
        subtests,
    ):
        for guest_load_time_period in GUEST_LOAD_TIME_PERIODS:
            with subtests.test(msg=guest_load_time_period):
                validate_metric_value_greater_than_initial_value(
                    prometheus=prometheus,
                    metric_name=f"{guest_load_time_period}{{name='{fedora_vm_with_stress_ng.name}'}}",
                    initial_value=0,
                )
