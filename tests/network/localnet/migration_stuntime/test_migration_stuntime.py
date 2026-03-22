"""
OVN localnet (OVS bridge) migration stuntime measurement tests over live migration.

Tests measure the connectivity gap (stuntime) during VM live migration on OVN localnet
secondary network, for both IPv4 and IPv6, for regression detection.
Stuntime is defined as the connectivity gap from last successful reply before loss
to first successful reply after recovery.

Stuntime is measured using ICMP ping from client to server in 0.1s intervals.
The under-test VMs are configured on an OVN localnet secondary network, with a single interface,
on which IPv4/IPv6 static addresses will be defined according to the environment the test runs on.

Client - The connectivity initiator VM that runs continuous ping toward the server VM.
Server - The connectivity listener VM that receives the ping and responds.

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/stuntime_measurement.md
"""

import pytest

from libs.vm.affinity import new_pod_anti_affinity
from tests.network.localnet.migration_stuntime.libstuntime import (
    SERVER_VM_LABEL,
    STUNTIME_THRESHOLD_SECONDS,
    compute_stuntime,
)
from utilities.virt import migrate_vm_and_verify

pytestmark = [pytest.mark.tier3]

"""
Preconditions:
    - Shared under-test server VM on OVN localnet secondary network, for the IP family from ip_family parametrization.
    - Shared under-test client VM on OVN localnet secondary network, for that same IP family,
      initially running on the same node as the server VM.
"""


@pytest.mark.incremental
class TestMigrationStuntime:
    @pytest.mark.parametrize(
        "active_ping",
        [
            pytest.param(4, id="ipv4", marks=[pytest.mark.polarion("CNV-15258"), pytest.mark.ipv4]),
            pytest.param(6, id="ipv6", marks=[pytest.mark.polarion("CNV-15272"), pytest.mark.ipv6]),
        ],
        indirect=True,
    )
    def test_client_migrates_off_server_node(
        self,
        admin_client,
        localnet_stuntime_client_vm,
        active_ping,
    ):
        """
        Test that measured stuntime does not exceed the global threshold when the client
        VM migrates from the node hosting the server VM into a different node.

        Parametrize:
            - active_ping:
                - ipv4 [Markers: ipv4]
                - ipv6 [Markers: ipv6]

        Preconditions:
            - Under-test server VM on OVN localnet secondary network, for the IP family from ip_family parametrization.
            - Under-test client VM on OVN localnet secondary network, for that same IP family,
              running on the same node as the server VM.
            - Ping initiated from the client to the server.

        Steps:
            1. Initiate live migration of the client VM to a node different from the node hosting the server VM
               and wait for migration completion.
            2. Stop the continuous ping.
            3. Compute stuntime from the ping results.

        Expected:
            - Measured stuntime does not exceed the global threshold.
        """
        localnet_stuntime_client_vm.set_template_affinity(affinity=new_pod_anti_affinity(label=SERVER_VM_LABEL))
        migrate_vm_and_verify(vm=localnet_stuntime_client_vm, client=admin_client)
        active_ping.stop()
        _, _, lost = active_ping.report()
        measured_stuntime = compute_stuntime(lost_packets=lost)
        assert measured_stuntime <= STUNTIME_THRESHOLD_SECONDS, (
            f"Stuntime {measured_stuntime}s exceeds threshold ({STUNTIME_THRESHOLD_SECONDS}s)"
        )

    @pytest.mark.polarion("CNV-15259")
    def test_client_migrates_between_non_server_nodes(self):
        """
        Test that measured stuntime does not exceed the global threshold when the client VM migrates between nodes
        while the client and server VMs remain on different nodes.

        Preconditions:
            - Under-test server VM on OVN localnet secondary network, for the IP family from ip_family parametrization.
            - Under-test client VM on OVN localnet secondary network, for that same IP family,
              running on a worker node other than the node hosting the server VM.
            - Ping initiated from the client to the server.

        Steps:
            1. Initiate live migration of the client VM to a node different from the node hosting the server VM
               and wait for migration completion.
            2. Stop the continuous ping.
            3. Compute stuntime from the ping results.

        Expected:
            - Measured stuntime does not exceed the global threshold.
        """

    @pytest.mark.polarion("CNV-15260")
    def test_client_migrates_to_server_node(self):
        """
        Test that measured stuntime does not exceed the global threshold when the client VM migrates
        from a node other than the node hosting the server VM onto the node hosting the server VM.

        Preconditions:
            - Under-test server VM on OVN localnet secondary network, for the IP family from ip_family parametrization.
            - Under-test client VM on OVN localnet secondary network, for that same IP family,
              running on a worker node other than the node hosting the server VM.
            - Ping initiated from the client to the server.

        Steps:
            1. Initiate live migration of the client VM to the node hosting the server VM
               and wait for migration completion.
            2. Stop the continuous ping.
            3. Compute stuntime from the ping results.

        Expected:
            - Measured stuntime does not exceed the global threshold.
        """

    @pytest.mark.polarion("CNV-15261")
    def test_server_migrates_off_client_node(self):
        """
        Test that measured stuntime does not exceed the global threshold when the server
        VM migrates from the node hosting the client VM into a different node.

        Preconditions:
            - Under-test server VM on OVN localnet secondary network, for the IP family from ip_family parametrization.
            - Under-test client VM on OVN localnet secondary network, for that same IP family,
              running on the same node as the server VM.
            - Ping initiated from the client to the server.

        Steps:
            1. Initiate live migration of the server VM to a node different from the node hosting the client VM
               and wait for migration completion.
            2. Stop the continuous ping.
            3. Compute stuntime from the ping results.

        Expected:
            - Measured stuntime does not exceed the global threshold.
        """

    @pytest.mark.polarion("CNV-15262")
    def test_server_migrates_between_non_client_nodes(self):
        """
        Test that measured stuntime does not exceed the global threshold when the server VM migrates between nodes
        while the client and server VMs remain on different nodes.

        Preconditions:
            - Under-test server VM on OVN localnet secondary network, for the IP family from ip_family parametrization.
            - Under-test client VM on OVN localnet secondary network, for that same IP family,
              running on a worker node other than the node hosting the server VM (before and after migration).
            - Ping initiated from the client to the server.

        Steps:
            1. Initiate live migration of the server VM to a node different from the node hosting the client VM
               and wait for migration completion.
            2. Stop the continuous ping.
            3. Compute stuntime from the ping results.

        Expected:
            - Measured stuntime does not exceed the global threshold.
        """

    @pytest.mark.polarion("CNV-15263")
    def test_server_migrates_to_client_node(self):
        """
        Test that measured stuntime does not exceed the global threshold when the server VM migrates from a node
        other than the node hosting the client VM onto the node hosting the client VM.

        Preconditions:
            - Under-test server VM on OVN localnet secondary network, for the IP family from ip_family parametrization.
            - Under-test client VM on OVN localnet secondary network, for that same IP family,
              running on a worker node other than the node hosting the server VM.
            - Ping initiated from the client to the server.

        Steps:
            1. Initiate live migration of the server VM to the node hosting the client VM
               and wait for migration completion.
            2. Stop the continuous ping.
            3. Compute stuntime from the ping results.

        Expected:
            - Measured stuntime does not exceed the global threshold.
        """

    test_client_migrates_between_non_server_nodes.__test__ = False
    test_client_migrates_to_server_node.__test__ = False
    test_server_migrates_off_client_node.__test__ = False
    test_server_migrates_between_non_client_nodes.__test__ = False
    test_server_migrates_to_client_node.__test__ = False
