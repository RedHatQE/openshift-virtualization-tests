import logging

import pytest

from tests.network.non_functional.ip_persistence.libippersistence import monitor_vmi_events
from utilities.virt import migrate_vm_and_verify

LOGGER = logging.getLogger(__name__)

WATCHER_TIMEOUT_SECONDS = 300


@pytest.mark.incremental
class TestIpPersistence:
    @pytest.mark.polarion("CNV-14339")
    def test_ip_address_persistence(self, linux_bridge_vm_for_ip_persist):
        for event_vmi in monitor_vmi_events(vm=linux_bridge_vm_for_ip_persist, watcher_timeout=WATCHER_TIMEOUT_SECONDS):
            interfaces = event_vmi.status.interfaces
            assert interfaces, "VMI has no interfaces"
            assert len(interfaces) == 2, f"Expected 2 interfaces, got {len(interfaces)}"
            for iface in interfaces:
                assert iface.ipAddress, f"ipAddress missing on interface {iface.name}"

    @pytest.mark.polarion("CNV-14340")
    def test_ip_address_persistence_after_migration(self, linux_bridge_vm_for_ip_persist):
        migrate_vm_and_verify(vm=linux_bridge_vm_for_ip_persist)
        for event_vmi in monitor_vmi_events(
            vm=linux_bridge_vm_for_ip_persist, watcher_timeout=WATCHER_TIMEOUT_SECONDS, context="after migration"
        ):
            interfaces = event_vmi.status.interfaces
            assert interfaces, "VMI has no interfaces after migration"
            assert len(interfaces) == 2, f"Expected 2 interfaces, got {len(interfaces)}"
            for iface in interfaces:
                assert iface.ipAddress, f"ipAddress missing on interface {iface.name}"
