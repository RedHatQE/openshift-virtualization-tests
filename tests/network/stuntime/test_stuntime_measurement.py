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
    def test_migration_stuntime(self):
        """
        Test that measured stuntime during live migration does not exceed the per-scenario threshold.

        Markers:
            - pytest.mark.ipv4, pytest.mark.ipv6 (applied per ip_family value for selective runs).

        Parametrize:
            - ip_family: IP family used for connectivity downtime measurements.
              Values:
               - ipv4 (ping -D -O -i 0.1).
               - ipv6 (ping -6 -D -O -i 0.1).
            - migration_path: Direction of VM migration relative to the peer's node.
              Values:
               - co_located_to_remote (migrate from peer's node to a remote node).
               - remote_to_co_located (migrate from a remote node to peer's node).
               - remote_to_remote (migrate between two remote nodes).
            - ping_initiator: VM from which the ping command is launched toward the peer.
              Values:
               - migrated_vm (ping from the VM for migration toward the peer).
               - peer_vm (ping from the peer toward the VM for migration).

        Preconditions:
            - Running VM for migration on Linux bridge secondary network, running on worker1.
            - Running peer VM on Linux bridge secondary network, running on worker1.
            - Ping running at 100 ms intervals from ping_initiator VM to peer.
            - Predefined stuntime threshold to test against (per-scenario, derived from BM baseline runs).

        Steps:
            1. Restart ping before each parametrized run so the log captures only that run's connectivity gap.
            2. Initiate live migration of the VM for migration along the specified path.
            3. Parse ping output for connectivity gap (last success before loss to first success after recovery).
            4. Compare measured stuntime against per-scenario threshold.

        Expected:
            - Measured stuntime does not exceed the per-scenario threshold.
        """

    test_migration_stuntime.__test__ = False


class TestStuntimeOvnLocalnet:
    """Stuntime measurement on OVN localnet secondary network."""

    @pytest.mark.polarion("CNV-00000")
    def test_migration_stuntime(self):
        """
        Test that measured stuntime during live migration does not exceed the per-scenario threshold.

        Markers:
            - pytest.mark.ipv4, pytest.mark.ipv6 (applied per ip_family value for selective runs).

        Parametrize:
            - ip_family: IP family used for connectivity downtime measurements.
              Values:
               - ipv4 (ping -D -O -i 0.1).
               - ipv6 (ping -6 -D -O -i 0.1).
            - migration_path: Direction of VM migration relative to the peer's node.
              Values:
               - co_located_to_remote (migrate from peer's node to a remote node).
               - remote_to_co_located (migrate from a remote node to peer's node).
               - remote_to_remote (migrate between two remote nodes).
            - ping_initiator: VM from which the ping command is launched toward the peer.
              Values:
               - migrated_vm (ping from the VM for migration toward the peer).
               - peer_vm (ping from the peer toward the VM for migration).

        Preconditions:
            - Running VM for migration on OVN localnet secondary network, running on worker1.
            - Running peer VM on OVN localnet secondary network, running on worker1.
            - Ping running at 100 ms intervals from ping_initiator VM to peer.
            - Predefined stuntime threshold to test against (per-scenario, derived from BM baseline runs).

        Steps:
            1. Restart ping before each parametrized run so the log captures only that run's connectivity gap.
            2. Initiate live migration of the VM for migration along the specified path.
            3. Parse ping output for connectivity gap (last success before loss to first success after recovery).
            4. Compare measured stuntime against per-scenario threshold.

        Expected:
            - Measured stuntime does not exceed the per-scenario threshold.
        """

    test_migration_stuntime.__test__ = False
