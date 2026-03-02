"""
VM stuntime measurement during live migration on secondary networks.

Tests measure the connectivity gap (stuntime) during VM live migration across
Linux bridge and OVN localnet secondary networks, for regression detection.

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

        Markers:
            - ipv4

        Parametrize:
            - migration_path: [static_to_different, different_to_static, between_different]
              (relative to static VM's node: from static's node to different; from different to
              static's node; between two nodes both different from static's node). See STP II.1.
            - ping_initiator: [migrated_vm, static_vm]

        Preconditions:
            - Running Fedora migrated-VM on Linux bridge secondary network, running on worker1.
            - Running Fedora static-VM on Linux bridge secondary network, running on worker1.
            - Ping running at 100 ms intervals (ping -D -O -i 0.1) from initiator VM to peer.

        Steps:
            1. Initiate live migration of the migrated VM along the specified path.
            2. Parse ping output for connectivity gap (last success before loss to first success after recovery).
            3. Compare measured stuntime against per-scenario threshold.

        Expected:
            - Measured stuntime does not exceed the scenario threshold (min(max×4, 5s)).
        """

    test_stuntime.__test__ = False


class TestStuntimeOvnLocalnet:
    """Stuntime measurement on OVN localnet secondary network."""

    @pytest.mark.polarion("CNV-00000")
    def test_stuntime(self):
        """
        Test that measured stuntime during live migration does not exceed the per-scenario threshold.

        Markers:
            - ipv4

        Parametrize:
            - migration_path: [static_to_different, different_to_static, between_different]
              (relative to static VM's node: from static's node to different; from different to
              static's node; between two nodes both different from static's node). See STP II.1.
            - ping_initiator: [migrated_vm, static_vm]

        Preconditions:
            - Running Fedora migrated-VM on OVN localnet secondary network, running on worker1.
            - Running Fedora static-VM on OVN localnet secondary network, running on worker1.
            - Ping running at 100 ms intervals (ping -D -O -i 0.1) from initiator VM to peer.

        Steps:
            1. Initiate live migration of the migrated VM along the specified path.
            2. Parse ping output for connectivity gap (last success before loss to first success after recovery).
            3. Compare measured stuntime against per-scenario threshold.

        Expected:
            - Measured stuntime does not exceed the scenario threshold (min(max×4, 5s)).
        """

    test_stuntime.__test__ = False
