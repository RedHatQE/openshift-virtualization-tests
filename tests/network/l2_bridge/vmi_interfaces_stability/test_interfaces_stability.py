from typing import Final

import pytest

from libs.net.vmspec import lookup_iface_status, lookup_primary_network
from tests.network.l2_bridge.vmi_interfaces_stability.lib_helpers import (
    assert_interfaces_stable,
    monitor_vmi_events,
)
from utilities.virt import migrate_vm_and_verify

STABILITY_PERIOD_IN_SECONDS: Final[int] = 300


@pytest.mark.incremental
@pytest.mark.tier3
class TestInterfacesStability:
    @pytest.mark.polarion("CNV-14339")
    def test_interfaces_stability(self, running_linux_bridge_vm, stable_ips):
        for vmi_obj in monitor_vmi_events(vm=running_linux_bridge_vm, timeout=STABILITY_PERIOD_IN_SECONDS):
            assert_interfaces_stable(stable_ips=stable_ips, vmi=vmi_obj, expected_num_ifaces=len(stable_ips))

    @pytest.mark.polarion("CNV-14340")
    def test_interfaces_stability_after_migration(self, running_linux_bridge_vm, stable_ips):
        migrate_vm_and_verify(vm=running_linux_bridge_vm)
        primary_network = lookup_primary_network(vm=running_linux_bridge_vm)
        primary_iface = lookup_iface_status(
            vm=running_linux_bridge_vm,
            iface_name=primary_network.name,
            predicate=lambda iface: bool(iface["ipAddress"]),
        )
        stable_ips[primary_network.name] = primary_iface.ipAddress
        for vmi_obj in monitor_vmi_events(vm=running_linux_bridge_vm, timeout=STABILITY_PERIOD_IN_SECONDS):
            assert_interfaces_stable(stable_ips=stable_ips, vmi=vmi_obj, expected_num_ifaces=len(stable_ips))

    @pytest.mark.polarion("CNV-16025")
    def test_interfaces_stability_after_guest_agent_restart(self, running_linux_bridge_vm, stable_ips):
        """
        Test that interface IPs remain stable after restarting the guest agent inside the VM.

        Jira: https://redhat.atlassian.net/browse/CNV-85415 # <skip-jira-utils-check>

        Preconditions:
            - Running Fedora VM with two secondary Linux bridge network interfaces
            - Secondary interface IPs are stable and reported by the guest agent

        Steps:
            1. Restart the qemu-guest-agent service using systemctl inside the VM

        Expected:
            - Interface IPs reported in VMI status remain unchanged throughout the monitoring period
        """
        running_linux_bridge_vm.console(
            commands=["sudo systemctl restart qemu-guest-agent.service"],
            timeout=30,
        )
        for vmi_obj in monitor_vmi_events(vm=running_linux_bridge_vm, timeout=STABILITY_PERIOD_IN_SECONDS):
            assert_interfaces_stable(stable_ips=stable_ips, vmi=vmi_obj, expected_num_ifaces=len(stable_ips))
