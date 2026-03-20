__test__ = False

import pytest

"""
Markers:
    - IPv4

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


@pytest.mark.polarion("CNV-15227")
def test_connectivity_between_udn_vms(self):
    """
    Preconditions:
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Running connectivity reference VM with a primary EVPN-enabled CUDN.

    Steps:
    1. Initiate TCP traffic between the two CUDN VMs.

    Checks:
    - VMs successfully communicate with each other.
    """


@pytest.mark.polarion("CNV-15228")
def test_stretched_l2_connectivity_udn_vm_and_external_provider(self):
    """
    Preconditions:
    - External Source Provider L2 endpoint.
    - Running target under-test VM with a primary EVPN-enabled CUDN.

    Steps:
    1. Initiate TCP traffic between the target under-test VM and the external L2 endpoint.

    Checks:
    - The VM successfully communicates with the the external L2 endpoint.
    """


@pytest.mark.polarion("CNV-15229")
def test_stretched_l2_connectivity_is_preserved_over_live_migration(self):
    """
    Preconditions:
    - External Source Provider L2 endpoint.
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Established TCP connectivity between the target under-test VM and the external L2 endpoint.

    Steps:
    1. Live-migrate the target under-test VM and wait for completion.

    Checks:
    - The initial TCP connection is preserved (no disconnection).
    """


@pytest.mark.polarion("CNV-15230")
def test_routed_l3_connectivity_udn_vm_and_external_provider(self):
    """
    Preconditions:
    - External Source Provider L3 endpoint.
    - Running target under-test VM with a primary EVPN-enabled CUDN.

    Steps:
    1. Initiate TCP traffic between the target under-test VM and the external L3 endpoint.

    Checks:
    - The VM successfully communicates with the external L3 endpoint.
    """


@pytest.mark.polarion("CNV-15231")
def test_routed_l3_connectivity_is_preserved_over_live_migration(self):
    """
    Preconditions:
    - External Source Provider L3 endpoint.
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Established TCP connectivity between the target under-test VM and the external L3 endpoint.

    Steps:
    1. Live-migrate UDN VM and wait for completion.

    Checks:
    - The initial TCP connection is preserved (no disconnection).
    """


@pytest.mark.polarion("CNV-15232")
def test_connectivity_after_udn_vm_cold_reboot(self):
    """
    Preconditions:
    - External Source Provider L2 and L3 endpoints.
    - Running target under-test VM with a primary EVPN-enabled CUDN.
    - Running connectivity reference VM with a primary EVPN-enabled CUDN.

    Steps:
    1. Restart the target under-test VM.
    3. Initiate TCP traffic between target under-test VM and the external endpoints/connectivity reference VM.

    Checks:
    - New connections are established after the cold reboot.
    """


@pytest.mark.polarion("CNV-15233")
def test_source_provider_migration(self):
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

    Checks:
    - New connections are established after new UDN VM deployment.
    """
