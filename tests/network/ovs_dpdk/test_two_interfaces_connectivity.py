"""
OVS-DPDK VM with two interfaces connectivity tests.

Markers:
    - ovs_dpdk
    - special_infra
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from libs.net.vmspec import lookup_iface_status_ip
from tests.network.libs.connectivity import poll_tcp_connectivity
from tests.network.ovs_dpdk.libovsdpdk import (
    GUEST_OVS_DPDK_IFACE_NAME,
    GUEST_OVS_DPDK_SECOND_IFACE_NAME,
    OVS_DPDK_INTERFACE_NAME,
    OVS_DPDK_SECOND_INTERFACE_NAME,
)

if TYPE_CHECKING:
    from libs.vm.vm import BaseVirtualMachine


@pytest.mark.ovs_dpdk
@pytest.mark.special_infra
@pytest.mark.incremental
@pytest.mark.parametrize(
    "ip_family",
    [
        pytest.param(4, marks=pytest.mark.ipv4, id="ipv4"),
        pytest.param(6, marks=pytest.mark.ipv6, id="ipv6"),
    ],
)
class TestReachabilityByVlan:
    """
    Tests for a VM with two OVS-DPDK network interfaces, each backed by a separate
    ResourceClaimTemplate-generated claim isolated on its own VLAN, traffic flows independently
    on each interface and does not cross between the two VLANs.

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Two ResourceClaimTemplates, each generating a claim for one OVS-DPDK device,
          each claim configured with a different VLAN tag (VLAN-A, VLAN-B)
        - Running reference VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)
        - Running under-test VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)
    """

    def test_no_connectivity_across_vlans(
        self,
        ip_family: int,
        under_test_ref_dual_claim_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
    ):
        """
        [NEGATIVE] Test that an under-test VM with two OVS-DPDK network interfaces, each backed by a
        separate ResourceClaimTemplate-generated claim isolated on its own VLAN, has no cross-VLAN
        TCP connectivity to the reference VM.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running reference VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)
            - Running under-test VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)

        Steps:
            1. Attempt TCP connection from the under-test VM's first OVS-DPDK interface (VLAN-A) to the
               reference VM's second OVS-DPDK interface (VLAN-B)

        Expected:
            - TCP connectivity across the two VLANs (first interface on VLAN-A to VLAN-B) fails
        """
        client_vm, server_vm = under_test_ref_dual_claim_running_vms
        server_ip = str(
            lookup_iface_status_ip(
                vm=server_vm,
                iface_name=OVS_DPDK_SECOND_INTERFACE_NAME,
                ip_family=ip_family,
            )
        )
        poll_tcp_connectivity(
            client_vm=client_vm,
            server_vm=server_vm,
            server_ip=server_ip,
            client_bind_dev=GUEST_OVS_DPDK_IFACE_NAME,
            server_bind_dev=GUEST_OVS_DPDK_SECOND_IFACE_NAME,
            expect_connectivity=False,
        )

    def test_first_network(
        self,
        ip_family: int,
        under_test_ref_dual_claim_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
    ):
        """
        Test that an under-test VM with two OVS-DPDK network interfaces, each backed by a separate
        ResourceClaimTemplate-generated claim isolated on its own VLAN, has TCP connectivity to the
        reference VM over the first OVS-DPDK interface.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running reference VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)
            - Running under-test VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)

        Steps:
            1. Establish TCP connection from the under-test VM to the reference VM over the first OVS-DPDK interface

        Expected:
            - TCP connectivity between the VMs is established over the first OVS-DPDK interface
        """
        client_vm, server_vm = under_test_ref_dual_claim_running_vms
        server_ip = str(lookup_iface_status_ip(vm=server_vm, iface_name=OVS_DPDK_INTERFACE_NAME, ip_family=ip_family))
        poll_tcp_connectivity(
            client_vm=client_vm,
            server_vm=server_vm,
            server_ip=server_ip,
            client_bind_dev=GUEST_OVS_DPDK_IFACE_NAME,
            server_bind_dev=GUEST_OVS_DPDK_IFACE_NAME,
        )

    def test_second_network(
        self,
        ip_family: int,
        under_test_ref_dual_claim_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
    ):
        """
        Test that an under-test VM with two OVS-DPDK network interfaces, each backed by a separate
        ResourceClaimTemplate-generated claim isolated on its own VLAN, has TCP connectivity to the
        reference VM over the second OVS-DPDK interface.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running reference VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)
            - Running under-test VM with two OVS-DPDK interfaces, one per claim (VLAN-A, VLAN-B)

        Steps:
            1. Establish TCP connection from the under-test VM to the reference VM over the second OVS-DPDK interface

        Expected:
            - TCP connectivity between the VMs is established over the second OVS-DPDK interface
        """
        client_vm, server_vm = under_test_ref_dual_claim_running_vms
        server_ip = str(
            lookup_iface_status_ip(vm=server_vm, iface_name=OVS_DPDK_SECOND_INTERFACE_NAME, ip_family=ip_family)
        )
        poll_tcp_connectivity(
            client_vm=client_vm,
            server_vm=server_vm,
            server_ip=server_ip,
            client_bind_dev=GUEST_OVS_DPDK_SECOND_IFACE_NAME,
            server_bind_dev=GUEST_OVS_DPDK_SECOND_IFACE_NAME,
        )
