"""
OVN localnet (OVS bridge) migration stuntime measurement tests over live migration.

Tests measure the connectivity gap (stuntime) during VM live migration on OVN localnet
secondary network, for both IPv4 and IPv6, for regression detection.
Stuntime is defined as the connectivity gap from last successful reply before loss
to first successful reply after recovery.

Stuntime is measured using continuous ICMP ping from client to server.
The under-test VMs are configured on an OVN localnet secondary network, with a single interface,
on which IPv4/IPv6 static addresses will be defined according to the environment the test runs on.

Client - The connectivity initiator VM that runs continuous ping toward the server VM.
Server - The connectivity listener VM that receives the ping and responds.

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/stuntime_measurement.md
"""

import json
import logging

import pytest

from libs.vm.affinity import new_pod_affinity, new_pod_anti_affinity
from tests.network.libs.stuntime import (
    CLIENT_VM_LABEL,
    SERVER_VM_LABEL,
    STUNTIME_THRESHOLD_SECONDS,
    measure_stuntime,
)
from utilities.virt import migrate_vm_and_verify

_LOGGER = logging.getLogger(__name__)


def _log_affinity_state(client_vm, server_vm):
    for label, vm in [("CLIENT", client_vm), ("SERVER", server_vm)]:
        vm_name = vm.name
        vmi_name = vm.vmi.name
        pod_name = vm.vmi.virt_launcher_pod.name
        vm_affinity = vm.instance.to_dict()["spec"]["template"]["spec"].get("affinity")
        vmi_affinity = vm.vmi.instance.to_dict()["spec"].get("affinity")
        pod_affinity = vm.vmi.virt_launcher_pod.instance.to_dict()["spec"].get("affinity")
        _LOGGER.info(f"{label} VM TEMPLATE ({vm_name}) affinity: {json.dumps(vm_affinity, indent=2)}")
        _LOGGER.info(f"{label} VMI ({vmi_name}) affinity: {json.dumps(vmi_affinity, indent=2)}")
        _LOGGER.info(f"{label} POD ({pod_name}) affinity: {json.dumps(pod_affinity, indent=2)}")


def _has_stuntime_affinity_rules(affinity_section):
    """Check if an affinity section contains stuntime label rules (not kubevirt-internal ones)."""
    for rule in affinity_section.get("requiredDuringSchedulingIgnoredDuringExecution", []):
        label_selector = rule.get("labelSelector", {})
        for expr in label_selector.get("matchExpressions", []):
            if expr.get("key", "").startswith("stuntime."):
                return True
    return False


def _assert_vm_placement(client_vm, server_vm, same_node):
    client_node = client_vm.vmi.instance.status.nodeName
    server_node = server_vm.vmi.instance.status.nodeName
    _LOGGER.info(f"CLIENT on {client_node}, SERVER on {server_node}")
    if same_node:
        assert client_node == server_node, (
            f"Expected VMs on same node, but CLIENT on {client_node} and SERVER on {server_node}"
        )
    else:
        assert client_node != server_node, f"Expected VMs on different nodes, but both on {client_node}"


def _assert_affinity_after_migration(vm, expected_type):
    vm_name = vm.name
    vmi_name = vm.vmi.name
    pod_name = vm.vmi.virt_launcher_pod.name
    vm_affinity = vm.instance.to_dict()["spec"]["template"]["spec"].get("affinity")
    vmi_affinity = vm.vmi.instance.to_dict()["spec"].get("affinity")
    pod_affinity = vm.vmi.virt_launcher_pod.instance.to_dict()["spec"].get("affinity")
    stale_type = "podAntiAffinity" if expected_type == "podAffinity" else "podAffinity"
    _LOGGER.info(f"VM TEMPLATE ({vm_name}) affinity: {json.dumps(vm_affinity, indent=2)}")
    _LOGGER.info(f"VMI ({vmi_name}) affinity AFTER migration: {json.dumps(vmi_affinity, indent=2)}")
    _LOGGER.info(f"POD ({pod_name}) affinity AFTER migration: {json.dumps(pod_affinity, indent=2)}")
    assert expected_type in vm_affinity, f"VM template ({vm_name}) missing {expected_type}: {vm_affinity}"
    assert expected_type in vmi_affinity, f"VMI ({vmi_name}) missing {expected_type}: {vmi_affinity}"
    assert stale_type not in vmi_affinity, f"VMI ({vmi_name}) has stale {stale_type}: {vmi_affinity}"
    assert expected_type in pod_affinity, f"POD ({pod_name}) missing {expected_type}: {pod_affinity}"
    if stale_type in pod_affinity:
        assert not _has_stuntime_affinity_rules(pod_affinity[stale_type]), (
            f"POD ({pod_name}) has stale stuntime {stale_type}: {pod_affinity[stale_type]}"
        )


pytestmark = [pytest.mark.tier3]

"""
Preconditions:
    - Under-test server VM on OVN localnet secondary network, for the IP family from ip_family parametrization.
    - Under-test client VM on OVN localnet secondary network, for that same IP family,
      initially running on the same node as the server VM.
"""


@pytest.mark.incremental
@pytest.mark.parametrize(
    "ip_family",
    [
        pytest.param(4, marks=pytest.mark.ipv4, id="ipv4"),
        pytest.param(6, marks=pytest.mark.ipv6, id="ipv6"),
    ],
    indirect=True,
)
class TestMigrationStuntime:
    """
    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]
    """

    @pytest.mark.polarion("CNV-15258")
    def test_client_migrates_off_server_node(
        self, admin_client, ip_family, localnet_stuntime_client_vm, localnet_stuntime_server_vm, active_ping
    ):
        """
        Test that measured stuntime does not exceed the global threshold when the client
        VM migrates from the node hosting the server VM into a different node.

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
        localnet_stuntime_client_vm.wait_for_vmi_affinity()
        try:
            migrate_vm_and_verify(vm=localnet_stuntime_client_vm, client=admin_client)
        except Exception:
            _log_affinity_state(client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm)
            raise
        _assert_affinity_after_migration(vm=localnet_stuntime_client_vm, expected_type="podAntiAffinity")
        _assert_vm_placement(
            client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm, same_node=False
        )
        measured_stuntime = measure_stuntime(active_ping=active_ping)
        assert measured_stuntime <= STUNTIME_THRESHOLD_SECONDS, (
            f"Stuntime {measured_stuntime}s exceeds threshold ({STUNTIME_THRESHOLD_SECONDS}s)"
        )

    @pytest.mark.polarion("CNV-15259")
    def test_client_migrates_between_non_server_nodes(
        self, admin_client, ip_family, localnet_stuntime_client_vm, localnet_stuntime_server_vm, active_ping
    ):
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
        try:
            migrate_vm_and_verify(vm=localnet_stuntime_client_vm, client=admin_client)
        except Exception:
            _log_affinity_state(client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm)
            raise
        _assert_vm_placement(
            client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm, same_node=False
        )
        measured_stuntime = measure_stuntime(active_ping=active_ping)
        assert measured_stuntime <= STUNTIME_THRESHOLD_SECONDS, (
            f"Stuntime {measured_stuntime}s exceeds threshold ({STUNTIME_THRESHOLD_SECONDS}s)"
        )

    @pytest.mark.polarion("CNV-15260")
    def test_client_migrates_to_server_node(
        self, admin_client, ip_family, localnet_stuntime_client_vm, localnet_stuntime_server_vm, active_ping
    ):
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
        localnet_stuntime_client_vm.set_template_affinity(affinity=new_pod_affinity(label=SERVER_VM_LABEL))
        localnet_stuntime_client_vm.wait_for_vmi_affinity()
        try:
            migrate_vm_and_verify(vm=localnet_stuntime_client_vm, client=admin_client)
        except Exception:
            _log_affinity_state(client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm)
            raise
        _assert_affinity_after_migration(vm=localnet_stuntime_client_vm, expected_type="podAffinity")
        _assert_vm_placement(
            client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm, same_node=True
        )
        measured_stuntime = measure_stuntime(active_ping=active_ping)
        assert measured_stuntime <= STUNTIME_THRESHOLD_SECONDS, (
            f"Stuntime {measured_stuntime}s exceeds threshold ({STUNTIME_THRESHOLD_SECONDS}s)"
        )

    @pytest.mark.polarion("CNV-15261")
    def test_server_migrates_off_client_node(
        self, admin_client, ip_family, localnet_stuntime_client_vm, localnet_stuntime_server_vm, active_ping
    ):
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
        localnet_stuntime_server_vm.set_template_affinity(affinity=new_pod_anti_affinity(label=CLIENT_VM_LABEL))
        localnet_stuntime_server_vm.wait_for_vmi_affinity()
        try:
            migrate_vm_and_verify(vm=localnet_stuntime_server_vm, client=admin_client)
        except Exception:
            _log_affinity_state(client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm)
            raise
        _assert_affinity_after_migration(vm=localnet_stuntime_server_vm, expected_type="podAntiAffinity")
        _assert_vm_placement(
            client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm, same_node=False
        )
        measured_stuntime = measure_stuntime(active_ping=active_ping)
        assert measured_stuntime <= STUNTIME_THRESHOLD_SECONDS, (
            f"Stuntime {measured_stuntime}s exceeds threshold ({STUNTIME_THRESHOLD_SECONDS}s)"
        )

    @pytest.mark.polarion("CNV-15262")
    def test_server_migrates_between_non_client_nodes(
        self, admin_client, ip_family, localnet_stuntime_client_vm, localnet_stuntime_server_vm, active_ping
    ):
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
        localnet_stuntime_server_vm.set_template_affinity(affinity=new_pod_anti_affinity(label=CLIENT_VM_LABEL))
        localnet_stuntime_server_vm.wait_for_vmi_affinity()
        try:
            migrate_vm_and_verify(vm=localnet_stuntime_server_vm, client=admin_client)
        except Exception:
            _log_affinity_state(client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm)
            raise
        _assert_affinity_after_migration(vm=localnet_stuntime_server_vm, expected_type="podAntiAffinity")
        _assert_vm_placement(
            client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm, same_node=False
        )
        measured_stuntime = measure_stuntime(active_ping=active_ping)
        assert measured_stuntime <= STUNTIME_THRESHOLD_SECONDS, (
            f"Stuntime {measured_stuntime}s exceeds threshold ({STUNTIME_THRESHOLD_SECONDS}s)"
        )

    @pytest.mark.polarion("CNV-15263")
    def test_server_migrates_to_client_node(
        self, admin_client, ip_family, localnet_stuntime_client_vm, localnet_stuntime_server_vm, active_ping
    ):
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
        localnet_stuntime_server_vm.set_template_affinity(affinity=new_pod_affinity(label=CLIENT_VM_LABEL))
        localnet_stuntime_server_vm.wait_for_vmi_affinity()
        try:
            migrate_vm_and_verify(vm=localnet_stuntime_server_vm, client=admin_client)
        except Exception:
            _log_affinity_state(client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm)
            raise
        _assert_affinity_after_migration(vm=localnet_stuntime_server_vm, expected_type="podAffinity")
        _assert_vm_placement(
            client_vm=localnet_stuntime_client_vm, server_vm=localnet_stuntime_server_vm, same_node=True
        )
        measured_stuntime = measure_stuntime(active_ping=active_ping)
        assert measured_stuntime <= STUNTIME_THRESHOLD_SECONDS, (
            f"Stuntime {measured_stuntime}s exceeds threshold ({STUNTIME_THRESHOLD_SECONDS}s)"
        )
