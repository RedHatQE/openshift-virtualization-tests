"""
VM to VM connectivity
"""

from ipaddress import ip_interface

import pytest

import utilities.network


@pytest.mark.polarion("CNV-3296")
@pytest.mark.ovs_brcnv
@pytest.mark.s390x
def test_connectivity_over_pod_network(
    disconnected_bond_port,
    running_ovs_bond_vma,
    running_ovs_bond_vmb,
):
    """
    Check connectivity
    """
    vma_ip = running_ovs_bond_vma.vmi.interfaces[0]["ipAddress"]
    vmb_ip = running_ovs_bond_vmb.vmi.interfaces[0]["ipAddress"]
    for vm, ip in zip([running_ovs_bond_vma, running_ovs_bond_vmb], [vmb_ip, vma_ip]):
        utilities.network.assert_ping_successful(
            src_vm=vm,
            dst_ip=ip_interface(ip).ip,
        )
