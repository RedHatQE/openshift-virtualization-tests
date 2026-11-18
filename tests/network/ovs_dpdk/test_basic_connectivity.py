"""
OVS-DPDK basic TCP connectivity tests, including connectivity preservation during live
migration of the under-test VM.

Preconditions:
    - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
    - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device

Markers:
    - ovs_dpdk
    - special_infra
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from libs.net.traffic_generator import client_server_active_connection, is_tcp_connection
from tests.network.ovs_dpdk.libovsdpdk import OVS_DPDK_INTERFACE_NAME

if TYPE_CHECKING:
    from libs.net.traffic_generator import TcpServer, VMTcpClient
    from libs.vm.vm import BaseVirtualMachine

pytestmark = [
    pytest.mark.ovs_dpdk,
    pytest.mark.special_infra,
]


@pytest.mark.parametrize(
    "ip_family",
    [
        pytest.param(4, marks=pytest.mark.ipv4, id="ipv4"),
        pytest.param(6, marks=pytest.mark.ipv6, id="ipv6"),
    ],
)
def test_basic_connectivity(
    ip_family: int,
    under_test_ref_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
):
    """
    Test that TCP connectivity from the under-test VM to the reference VM is successful,
    for the parametrized IP family.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4
            - ipv6

    Preconditions:
        - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device

    Steps:
        1. Establish TCP connection from the under-test VM to the reference VM

    Expected:
        - TCP connection between the VMs is successful
    """
    client_vm, server_vm = under_test_ref_running_vms
    with client_server_active_connection(
        client_vm=client_vm,
        server_vm=server_vm,
        spec_logical_network=OVS_DPDK_INTERFACE_NAME,
        ip_family=ip_family,
    ) as (tcp_client, tcp_server):
        assert is_tcp_connection(server=tcp_server, client=tcp_client), (
            f"TCP connectivity from {client_vm.name} to {server_vm.name} failed"
        )


@pytest.mark.parametrize(
    "ip_family",
    [
        pytest.param(4, marks=pytest.mark.ipv4, id="ipv4"),
        pytest.param(6, marks=pytest.mark.ipv6, id="ipv6"),
    ],
)
@pytest.mark.usefixtures("ovs_dpdk_under_test_migrated_vm")
def test_connectivity_is_preserved_during_live_migration(
    ip_family: int,
    ovs_dpdk_active_tcp_by_family: dict[int, tuple[VMTcpClient, TcpServer]],
):
    """
    Test that TCP connectivity from the under-test VM to the reference VM is preserved
    during live migration, for the parametrized IP family.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4
            - ipv6

    Preconditions:
        - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Active TCP connection established from the under-test VM to the reference VM
        - Live migration of the under-test VM has completed

        The migration runs as part of the setup rather than as a test step so a single
        migration is shared by all IP-family variants, and the connections are established
        before it, so their survival is what this test asserts.

    Steps:
        1. Verify TCP connectivity from the under-test VM to the reference VM

    Expected:
        - The active TCP connection from the under-test VM to the reference VM is preserved
          during the migration
    """
    client, server = ovs_dpdk_active_tcp_by_family[ip_family]
    assert is_tcp_connection(server=server, client=client), (
        f"TCP connection lost after live migration of {client.vm.name} over IPv{ip_family}"
    )
