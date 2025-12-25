import logging

import pytest

from tests.observability.metrics.constants import GUEST_LOAD_TIME_PERIODS
from tests.observability.metrics.utils import validate_metric_value_greater_than_initial_value
LOGGER = logging.getLogger(__name__)


class TestVMIGuestLoad:
    # TODO: when the pr for updating the fedora will be merged, adjust the test.
    @pytest.mark.polarion("CNV-12369")
    def test_kubevirt_vmi_guest_load(
        self,
        prometheus,
        fedora_vm_with_stress_ng,
        qemu_guest_agent_version_validated,
        initial_guest_load_metrics_values,
        stressed_vm_cpu_fedora,
    ):
        for guest_load_time_period in GUEST_LOAD_TIME_PERIODS:
            LOGGER.info(f"Testing {guest_load_time_period}")
            metric_name = f"{guest_load_time_period}{{name='{fedora_vm_with_stress_ng.name}'}}"
            validate_metric_value_greater_than_initial_value(
                prometheus=prometheus,
                metric_name=metric_name,
                initial_value=float(initial_guest_load_metrics_values[guest_load_time_period]),
            )
