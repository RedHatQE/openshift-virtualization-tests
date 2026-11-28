"""
OVS-DPDK network recovery tests: backing driver restart, VM restart and OVS restart.

Preconditions:
    - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
    - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
    - IPv4+IPv6 TCP connectivity works successfully between the under-test VM and the reference VM

Markers:
    - ovs_dpdk
    - special_infra
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from libs.net.vmspec import lookup_iface_status_ip
from tests.network.libs.connectivity import poll_tcp_connectivity
from tests.network.ovs_dpdk.libovsdpdk import OVS_DPDK_INTERFACE_NAME

if TYPE_CHECKING:
    from libs.vm.vm import BaseVirtualMachine

pytestmark = [
    pytest.mark.ovs_dpdk,
    pytest.mark.special_infra,
]


class TestConnectivityAfterDpdkBackingDriverRestart:
    """
    Tests for OVS-DPDK backing driver restart: existing VM remains reachable, new VM achieves
    connectivity, and the under-test VM remains reachable during live migration, after
    the driver is restarted on each worker node.

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - OVS-DPDK backing driver restart completed on each worker node and driver is operational
    """

    __test__ = False

    @pytest.mark.manual
    def test_connectivity_existing_vm(self):
        """
        Test that TCP connectivity from the under-test VM to the reference VM is successful after
        the OVS-DPDK backing driver is restarted, for the parametrized IP family.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device

        Steps:
            1. Poll TCP connectivity from the under-test VM to the reference VM

        Expected:
            - The new TCP connection to the reference VM is successful
        """

    @pytest.mark.manual
    def test_connectivity_new_vm(self):
        """
        Test that a newly created VM with a ResourceClaim-backed OVS-DPDK network device achieves
        TCP connectivity to the reference VM after the backing driver was restarted, for the
        parametrized IP family.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device

        Steps:
            1. Create and start a VM with a ResourceClaim-backed OVS-DPDK network device
            2. Poll TCP connectivity from the new VM to the reference VM

        Expected:
            - The new TCP connection to the reference VM is successful
        """

    @pytest.mark.manual
    def test_connectivity_is_preserved_during_live_migration(self):
        """
        Test that TCP connectivity from the under-test VM to the reference VM is preserved
        during live migration, after the OVS-DPDK backing driver was restarted on each worker
        node, for the parametrized IP family.

        STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

        Preconditions:
            - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
            - Active TCP connection established from the under-test VM to the reference VM

        Steps:
            1. Live-migrate the under-test VM and wait for migration completion

        Expected:
            - The active TCP connection from the under-test VM to the reference VM is preserved
              during the migration
        """


@pytest.mark.parametrize(
    "ip_family",
    [
        pytest.param(4, marks=pytest.mark.ipv4, id="ipv4"),
        pytest.param(6, marks=pytest.mark.ipv6, id="ipv6"),
    ],
)
def test_connectivity_after_vm_restart(
    ip_family: int,
    under_test_ref_vms_after_vm_restart: tuple[BaseVirtualMachine, BaseVirtualMachine],
):
    """
    Test that TCP connectivity from the under-test VM to the reference VM is successful
    after the under-test VM is restarted, for the parametrized IP family.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Running under-test VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - IPv4+IPv6 TCP connectivity works successfully between the under-test VM and the reference VM
        - Under-test VM is restarted and network interfaces report expected addresses

    Steps:
        1. Poll TCP connectivity from the under-test VM to the reference VM

    Expected:
        - The new TCP connection to the reference VM is successful
    """
    client_vm, server_vm = under_test_ref_vms_after_vm_restart
    server_ip = str(lookup_iface_status_ip(vm=server_vm, iface_name=OVS_DPDK_INTERFACE_NAME, ip_family=ip_family))
    assert poll_tcp_connectivity(
        client_vm=client_vm,
        server_vm=server_vm,
        server_ip=server_ip,
    ), f"TCP connectivity from {client_vm.name} to {server_vm.name} failed after VM restart"


@pytest.mark.manual
def test_connectivity_after_ovs_restart():
    """
    Test that TCP connectivity from the under-test VM to the reference VM is successful
    after OVS is restarted on the worker node hosting the under-test VM, for the
    parametrized IP family.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ovs-dpdk-tp-stp.md

    Parametrize:
        - ip_family:
            - ipv4 [Markers: ipv4]
            - ipv6 [Markers: ipv6]

    Preconditions:
        - Running under-test VM with a ResourceClaim-backed OVS-DPDK network device
        - Running reference VM with a ResourceClaimTemplate-backed OVS-DPDK network device
        - OVS on the worker node hosting the under-test VM is restarted and operational on that node

    Steps:
        1. Poll TCP connectivity from the under-test VM to the reference VM

    Expected:
        - The new TCP connection to the reference VM is successful
    """


test_connectivity_after_ovs_restart.__test__ = False
