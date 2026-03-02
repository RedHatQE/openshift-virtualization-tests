"""
VM stuntime measurement during live migration on secondary networks.

Tests measure the connectivity gap (stuntime) during VM live migration across
Linux bridge and OVN localnet secondary networks, for both IPv4 and IPv6,
for regression detection.

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/stuntime_measurement.md
"""

import pytest


class TestStuntimeLinuxBridge:
    """Stuntime measurement on Linux bridge secondary network."""

    @pytest.mark.polarion("CNV-00001")
    def test_stuntime(self):
        """
        Test that measured stuntime during live migration does not exceed the per-scenario threshold.

        Parametrize:
            - ip_family: IP family used for connectivity downtime measurements.
              Values:
               - ipv4 (pytest.mark.ipv4, ping -D -O -i 0.1).
               - ipv6 (pytest.mark.ipv6, ping -6 -D -O -i 0.1).
            - migration_path: Direction of VM migration relative to the static VM's node.
              Values:
               - static_to_different (migrate from static VM's node to a different node).
               - different_to_static (migrate from a different node to static VM's node).
               - between_different (migrate between two nodes, both different from static VM's node).
            - ping_initiator: VM from which the ping command is launched toward the peer.
              Values:
               - migrated_vm (ping from the VM for migration).
               - static_vm (ping from the VM that stays on its node).

        Preconditions:
            - Running VM for migration on Linux bridge secondary network, running on worker1.
            - Running static VM on Linux bridge secondary network, running on worker1.
            - Ping running at 100 ms intervals from ping_initiator VM to peer.
            - Predefined stuntime threshold to test against (per-scenario, derived from BM baseline runs).

        Steps:
            1. Initiate live migration of the VM for migration along the specified path.
            2. Parse ping output for connectivity gap (last success before loss to first success after recovery).
            3. Compare measured stuntime against per-scenario threshold.

        Expected:
            - Measured stuntime does not exceed the per-scenario threshold.
        """

    test_stuntime.__test__ = False


class TestStuntimeOvnLocalnet:
    """Stuntime measurement on OVN localnet secondary network."""

    @pytest.mark.polarion("CNV-00000")
    def test_stuntime(self):
        """
        Test that measured stuntime during live migration does not exceed the per-scenario threshold.

        Parametrize:
            - ip_family: IP family used for connectivity downtime measurements.
              Values:
               - ipv4 (pytest.mark.ipv4, ping -D -O -i 0.1).
               - ipv6 (pytest.mark.ipv6, ping -6 -D -O -i 0.1).
            - migration_path: Direction of VM migration relative to the static VM's node.
              Values:
               - static_to_different (migrate from static VM's node to a different node).
               - different_to_static (migrate from a different node to static VM's node).
               - between_different (migrate between two nodes, both different from static VM's node).
            - ping_initiator: VM from which the ping command is launched toward the peer.
              Values:
               - migrated_vm (ping from the VM for migration).
               - static_vm (ping from the VM that stays on its node).

        Preconditions:
            - Running VM for migration on OVN localnet secondary network, running on worker1.
            - Running static VM on OVN localnet secondary network, running on worker1.
            - Ping running at 100 ms intervals from ping_initiator VM to peer.
            - Predefined stuntime threshold to test against (per-scenario, derived from BM baseline runs).

        Steps:
            1. Initiate live migration of the VM for migration along the specified path.
            2. Parse ping output for connectivity gap (last success before loss to first success after recovery).
            3. Compare measured stuntime against per-scenario threshold.

        Expected:
            - Measured stuntime does not exceed the per-scenario threshold.
        """

    test_stuntime.__test__ = False
