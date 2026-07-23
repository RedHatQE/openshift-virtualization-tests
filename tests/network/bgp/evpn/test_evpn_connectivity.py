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

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

import pytest

from libs.net.ip import random_ipv4_address, random_ipv6_address
from libs.net.traffic_generator import active_tcp_connections, is_tcp_connection
from libs.net.vmspec import lookup_primary_network
from tests.network.bgp.evpn.libevpn import (
    EVPN_CUDN_NET_SEED,
    assert_evpn_workloads_connectivity,
    deploy_evpn_l2_endpoint,
    evpn_workloads_active_connections,
    teardown_evpn_l2_endpoint,
)
from utilities.virt import migrate_vm_and_verify

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from libs.net.traffic_generator import TcpServer
    from libs.vm.vm import BaseVirtualMachine
    from tests.network.bgp.evpn.libevpn import EndpointTcpClient


_L2_ENDPOINT_IPV4: str = random_ipv4_address(net_seed=EVPN_CUDN_NET_SEED, host_address=249)
_L2_ENDPOINT_IPV6: str = random_ipv6_address(net_seed=EVPN_CUDN_NET_SEED, host_address=249)


pytestmark = [
    pytest.mark.bgp,
    pytest.mark.ipv4,
    pytest.mark.usefixtures("evpn_setup_ready"),
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
    admin_client: DynamicClient,
    evpn_stretched_l2_active_connections: list[tuple[EndpointTcpClient, TcpServer]],
    vm_evpn_target: BaseVirtualMachine,
    subtests: pytest.Subtests,
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
    migrate_vm_and_verify(vm=vm_evpn_target, client=admin_client)
    for client, server in evpn_stretched_l2_active_connections:
        with subtests.test(f"IPv{ipaddress.ip_address(client.server_ip).version}"):
            assert is_tcp_connection(server=server, client=client)


@pytest.mark.polarion("CNV-15230")
def test_routed_l3_connectivity_udn_vm_and_external_provider(external_l3_endpoint, vm_evpn_target, subtests):
    """
    Preconditions:
    - External Source Provider L3 endpoint.
    - Running target under-test VM with a primary EVPN-enabled CUDN.

    Steps:
    1. Initiate TCP traffic between the target under-test VM and the external L3 endpoint.

    Expected:
    - The VM successfully communicates with the external L3 endpoint.
    """
    with evpn_workloads_active_connections(endpoint=external_l3_endpoint, vm=vm_evpn_target) as connections:
        for client, server in connections:
            with subtests.test(f"IPv{ipaddress.ip_address(client.server_ip).version}"):
                assert is_tcp_connection(server=server, client=client)


@pytest.mark.polarion("CNV-15231")
def test_routed_l3_connectivity_is_preserved_over_live_migration(
    admin_client: DynamicClient,
    evpn_routed_l3_active_connections: list[tuple[EndpointTcpClient, TcpServer]],
    vm_evpn_target: BaseVirtualMachine,
    subtests: pytest.Subtests,
):
    """
    Preconditions:
    - External Source Provider L3 endpoint.
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Established TCP connectivity between the target under-test VM and the external L3 endpoint.

    Steps:
    1. Live-migrate the target under-test VM and wait for completion.

    Expected:
    - The initial TCP connection is preserved (no disconnection).
    """
    migrate_vm_and_verify(vm=vm_evpn_target, client=admin_client)
    for client, server in evpn_routed_l3_active_connections:
        with subtests.test(f"IPv{ipaddress.ip_address(client.server_ip).version}"):
            assert is_tcp_connection(server=server, client=client)


@pytest.mark.polarion("CNV-15232")
def test_connectivity_after_udn_vm_cold_reboot(
    vm_evpn_target,
    vm_evpn_reference,
    external_l2_endpoint,
    external_l3_endpoint,
    subtests,
):
    """
    Preconditions:
    - External Source Provider L2 and L3 endpoints.
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Running connectivity reference VM with a primary EVPN-enabled CUDN.

    Steps:
    1. Restart the target under-test VM.
    2. Initiate TCP traffic between target under-test VM and the external endpoints/connectivity reference VM.

    Expected:
    - New connections are established after the cold reboot.
    """
    vm_evpn_target.restart(wait=True)
    vm_evpn_target.wait_for_agent_connected()

    assert_evpn_workloads_connectivity(
        target_vm=vm_evpn_target,
        ref_vm=vm_evpn_reference,
        l2_endpoint=external_l2_endpoint,
        l3_endpoint=external_l3_endpoint,
        subtests=subtests,
    )


@pytest.mark.polarion("CNV-15233")
@pytest.mark.order("last")
def test_source_provider_migration(
    external_l3_endpoint,
    cudn_evpn_layer2,
    vm_source_provider,
    vm_evpn_target,
    frr_external_pod,
    subtests,
):
    """
    Scenario emulates a migration of an external workload (Source Provider) into the OCP cluster as a CUDN VM,
    while preserving its IP and MAC addresses, and maintaining connectivity.

    Preconditions:
    - External Source Provider L2 and L3 endpoints.
    - Running connectivity reference VM with a primary EVPN-enabled CUDN.
    - TCP connectivity exists between the connectivity reference VM and the external L2 and L3 endpoints.
      Precondition is verified in preceding tests.

    Steps:
    1. Shut down/remove the external L2 endpoint.
    2. Deploy a VM on the OCP cluster connected to the primary EVPN CUDN using the exact same IP and MAC.
    3. Initiate TCP traffic between newly deployed VM and the external provider endpoints/connectivity reference VM.

    Expected:
    - New connections are established after new UDN VM deployment.
    """
    mac_vrf_vni = cudn_evpn_layer2.instance.spec.network.evpn.macVRF.vni

    teardown_evpn_l2_endpoint(pod=frr_external_pod.pod, vni=mac_vrf_vni)

    vm_source_provider.start(wait=True)
    vm_source_provider.wait_for_agent_connected()

    new_l2_endpoint = deploy_evpn_l2_endpoint(
        pod=frr_external_pod.pod,
        vni=mac_vrf_vni,
        endpoint_ips=[_L2_ENDPOINT_IPV4, _L2_ENDPOINT_IPV6],
    )

    assert_evpn_workloads_connectivity(
        target_vm=vm_evpn_target,
        ref_vm=vm_source_provider,
        l2_endpoint=new_l2_endpoint,
        l3_endpoint=external_l3_endpoint,
        subtests=subtests,
    )
