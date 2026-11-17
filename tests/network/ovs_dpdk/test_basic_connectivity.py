"""
OVS-DPDK basic TCP connectivity tests.

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
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

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
