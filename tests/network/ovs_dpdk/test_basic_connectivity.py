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

import pytest

from libs.net.ip import filter_link_local_addresses
from libs.net.vmspec import lookup_iface_status
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.connectivity import poll_tcp_connectivity
from utilities.constants.networking import OVS_DPDK_INTERFACE_NAME

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
    indirect=True,
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
        1. Verify TCP connectivity from the under-test VM to the reference VM

    Expected:
        - TCP connectivity between the VMs is established
    """
    under_test_vm, ref_vm = under_test_ref_running_vms
    ref_iface = lookup_iface_status(vm=ref_vm, iface_name=OVS_DPDK_INTERFACE_NAME)
    server_ips_for_family = [
        str(server_ip)
        for server_ip in filter_link_local_addresses(ip_addresses=ref_iface.ipAddresses)
        if server_ip.version == ip_family
    ]

    server_ip = server_ips_for_family[0]
    assert poll_tcp_connectivity(
        client_vm=under_test_vm,
        server_vm=ref_vm,
        server_ip=server_ip,
    ), f"TCP connectivity from {under_test_vm.name} to {ref_vm.name} at {server_ip} failed"
