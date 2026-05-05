"""
STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/EVPN.md

Markers:
    - bgp
    - ipv4

Preconditions:
    - OVN-K in Local Gateway Mode.
    - Enabled route advertisements in the cluster network resource.
    - External Source Provider: BGP router (Spine) + L2 and L3 endpoints behind the Spine (see README.md).
    - UDN supported namespace.
    - EVPN-enabled CUDN Layer2 (using MAC-VRF (L2) and IP-VRF (L3)) with the same subnet as the external L2 endpoint.
    - BGP EVPN sessions are established between the OCP nodes and the external router.
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Running connectivity reference VM with a primary EVPN-enabled CUDN.
"""

import ipaddress

import pytest

from libs.net.traffic_generator import active_tcp_connections, is_tcp_connection
from libs.net.vmspec import lookup_primary_network
from tests.network.bgp.evpn.libevpn import evpn_workloads_active_connections
from utilities.virt import migrate_vm_and_verify

pytestmark = [
    pytest.mark.bgp,
    pytest.mark.ipv4,
    pytest.mark.usefixtures("evpn_setup_ready"),
    pytest.mark.jira("CNV-86961", run=False),
]


@pytest.mark.polarion("CNV-15227")
def test_connectivity_between_udn_vms(vm_evpn_target, vm_evpn_reference, subtests):
    """
    Preconditions:
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Running connectivity reference VM with a primary EVPN-enabled CUDN.

    Steps:
    1. Initiate TCP traffic between the two CUDN VMs.

    Expected:
    - VMs successfully communicate with each other.
    """
    with active_tcp_connections(
        client_vm=vm_evpn_reference,
        server_vm=vm_evpn_target,
        iface_name=lookup_primary_network(vm=vm_evpn_target).name,
    ) as connections:
        for client, server in connections:
            with subtests.test(f"IPv{ipaddress.ip_address(client.server_ip).version}"):
                assert is_tcp_connection(server=server, client=client)


@pytest.mark.polarion("CNV-15228")
def test_stretched_l2_connectivity_udn_vm_and_external_provider(external_l2_endpoint, vm_evpn_target, subtests):
    """
    Preconditions:
    - External Source Provider L2 endpoint.
    - Running target under-test VM with a primary EVPN-enabled CUDN.

    Steps:
    1. Initiate TCP traffic between the target under-test VM and the external L2 endpoint.

    Expected:
    - The VM successfully communicates with the external L2 endpoint.
    """
    with evpn_workloads_active_connections(endpoint=external_l2_endpoint, vm=vm_evpn_target) as connections:
        for client, server in connections:
            with subtests.test(f"IPv{ipaddress.ip_address(client.server_ip).version}"):
                assert is_tcp_connection(server=server, client=client)


@pytest.mark.polarion("CNV-15229")
def test_stretched_l2_connectivity_is_preserved_over_live_migration(
    evpn_stretched_l2_active_connections,
    vm_evpn_target,
    subtests,
):
    """
    Preconditions:
    - External Source Provider L2 endpoint.
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Established TCP connectivity between the target under-test VM and the external L2 endpoint.

    Steps:
    1. Live-migrate the target under-test VM and wait for completion.

    Expected:
    - The initial TCP connection is preserved (no disconnection).
    """
    migrate_vm_and_verify(vm=vm_evpn_target)
    for client, server in evpn_stretched_l2_active_connections:
        with subtests.test(f"IPv{ipaddress.ip_address(client.server_ip).version}"):
            assert is_tcp_connection(server=server, client=client)


@pytest.mark.polarion("CNV-15230")
def test_routed_l3_connectivity_udn_vm_and_external_provider():
    """
    Preconditions:
    - External Source Provider L3 endpoint.
    - Running target under-test VM with a primary EVPN-enabled CUDN.

    Steps:
    1. Initiate TCP traffic between the target under-test VM and the external L3 endpoint.

    Expected:
    - The VM successfully communicates with the external L3 endpoint.
    """


test_routed_l3_connectivity_udn_vm_and_external_provider.__test__ = False


@pytest.mark.polarion("CNV-15231")
def test_routed_l3_connectivity_is_preserved_over_live_migration():
    """
    Preconditions:
    - External Source Provider L3 endpoint.
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Established TCP connectivity between the target under-test VM and the external L3 endpoint.

    Steps:
    1. Live-migrate UDN VM and wait for completion.

    Expected:
    - The initial TCP connection is preserved (no disconnection).
    """


test_routed_l3_connectivity_is_preserved_over_live_migration.__test__ = False


@pytest.mark.polarion("CNV-15232")
def test_connectivity_after_udn_vm_cold_reboot():
    """
    Preconditions:
    - External Source Provider L2 and L3 endpoints.
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Running connectivity reference VM with a primary EVPN-enabled CUDN.

    Steps:
    1. Restart the target under-test VM.
    3. Initiate TCP traffic between target under-test VM and the external endpoints/connectivity reference VM.

    Expected:
    - New connections are established after the cold reboot.
    """


test_connectivity_after_udn_vm_cold_reboot.__test__ = False


@pytest.mark.polarion("CNV-15233")
def test_source_provider_migration():
    """
    Scenario emulates a migration of an external workload (Source Provider) into the OCP cluster as a CUDN VM,
    while preserving its IP and MAC addresses, and maintaining connectivity.

    Preconditions:
    - External Source Provider L2 and L3 endpoints.
    - Running connectivity reference VM with a primary EVPN-enabled CUDN.
    - TCP connectivity exists between the connectivity reference VM and the external L2 and L3 endpoints.

    Steps:
    1. Shut down/remove the external L2 endpoint.
    2. Deploy a VM on the OCP cluster connected to the primary EVPN CUDN using the exact same IP and MAC.
    3. Initiate TCP traffic between newly deployed VM and the external provider endpoints/connectivity reference VM.

    Expected:
    - New connections are established after new UDN VM deployment.
    """


test_source_provider_migration.__test__ = False
