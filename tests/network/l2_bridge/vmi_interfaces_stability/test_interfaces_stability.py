from typing import Final

import pytest

from tests.network.l2_bridge.vmi_interfaces_stability.lib_helpers import (
    assert_interfaces_stable,
    monitor_vmi_events,
)
from utilities.virt import migrate_vm_and_verify

STABILITY_PERIOD_IN_SECONDS: Final[int] = 300


@pytest.mark.incremental
class TestInterfacesStability:
    @pytest.mark.polarion("CNV-14339")
    def test_interfaces_stability(self, running_linux_bridge_vm, stable_ips):
        for vmi_obj in monitor_vmi_events(vm=running_linux_bridge_vm, timeout=STABILITY_PERIOD_IN_SECONDS):
            assert_interfaces_stable(stable_ips=stable_ips, vmi=vmi_obj, expected_num_ifaces=len(stable_ips))

    @pytest.mark.polarion("CNV-14340")
    def test_interfaces_stability_after_migration(self, running_linux_bridge_vm, stable_ips):
        migrate_vm_and_verify(vm=running_linux_bridge_vm)
        for vmi_obj in monitor_vmi_events(vm=running_linux_bridge_vm, timeout=STABILITY_PERIOD_IN_SECONDS):
            assert_interfaces_stable(stable_ips=stable_ips, vmi=vmi_obj, expected_num_ifaces=len(stable_ips))
