"""EVPN Connectivity Tests

Tests are aimed to cover the EVPN integration for OpenShift Virtualization VMs.

STP Reference: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/EVPN.md
"""

__test__ = False

import pytest


class TestEVPNConnectivity:
    """
    Suite Preconditions:
    - OVN-K in Local Gateway Mode.
    - Enabled route advertisements in the cluster network resource.
    - Localnet NNCP and NAD are configured.
    - External FRR pod (Spine) is deployed and attached to localnet.
    - L2 and L3 external endpoints are configured behind the external FRR Spine.
    - UDN supported namespace.
    - EVPN-enabled CUDN Layer2 (using MAC-VRF (L2) and IP-VRF (L3)) with the same subnet as the external L2 endpoint.
    - VTEP CR is configured, allocating VXLAN IPs to the worker nodes.
    - RouteAdvertisements CR is applied.
    - FRRConfiguration CR is applied for CUDN.
    - BGP EVPN sessions are established between the OCP nodes and the external FRR.
    - 2 running VMs within the same EVPN CUDN.
    """

    @pytest.mark.polarion("CNV-00000")
    def test_connectivity_between_udn_vms(self):
        """
        Preconditions:
        - 2 running VMs within the same EVPN CUDN.

        Steps:
        1. Initiate TCP traffic between the two CUDN VMs.

        Checks:
        - VMs successfully communicate with each other.
        """

    @pytest.mark.polarion("CNV-00000")
    def test_stretched_l2_connectivity_udn_vm_and_external_provider(self):
        """
        Preconditions:
        - External Source Provider L2 endpoint.
        - Running UDN VM and its IP in the same subnet as the external Source Provider L2 endpoint.

        Steps:
        1. Initiate TCP traffic between the VM and the external L2 endpoint.

        Checks:
        - The VM successfully communicates with the external Source Provider on the same subnet.
        """

    @pytest.mark.polarion("CNV-00000")
    def test_stretched_l2_connectivity_is_preserved_over_live_migration(self):
        """
        Preconditions:
        - External Source Provider L2 endpoint.
        - Running UDN VM and its IP in the same subnet as the external Source Provider L2 endpoint.
        - Established TCP connectivity between UDN VM and external L2 endpoint.

        Steps:
        1. Live-migrate UDN VM and wait for completion.

        Checks:
        - The initial TCP connection is preserved (no disconnection).
        """

    @pytest.mark.polarion("CNV-00000")
    def test_routed_l3_connectivity_udn_vm_and_external_provider(self):
        """
        Preconditions:
        - External Provider L3 endpoint.
        - Running UDN VM with an IP in a different subnet than the external provider L3 endpoint.

        Steps:
        1. Initiate TCP traffic between the VM and the external provider L3 endpoint.

        Checks:
        - The VM successfully communicates with the external provider L3 endpoint.
        """

    @pytest.mark.polarion("CNV-00000")
    def test_routed_l3_connectivity_is_preserved_over_live_migration(self):
        """
        Preconditions:
        - External Provider L3 endpoint.
        - Running UDN VM with an IP in a different subnet than the external provider L3 endpoint.
        - Established TCP connectivity between UDN VM and external L3 endpoint.

        Steps:
        1. Live-migrate UDN VM and wait for completion.

        Checks:
        - The initial TCP connection is preserved (no disconnection).
        """

    @pytest.mark.polarion("CNV-00000")
    def test_connectivity_after_udn_vm_cold_reboot(self):
        """
        Preconditions:
        - External Provider L2/L3 endpoints.
        - 2 running VMs within the same EVPN CUDN.

        Steps:
        1. Stop the VM (any).
        2. Start the VM.
        3. Initiate TCP traffic between the VM and the external provider endpoints/another UDN VM.

        Checks:
        - New connections are established after the cold reboot.
        """

    @pytest.mark.polarion("CNV-00000")
    def test_source_provider_migration(self):
        """
        Scenario emulates a migration of an external workload (Source Provider) into the OCP cluster as a CUDN VM,
        while preserving its IP and MAC addresses, and maintaining connectivity.

        Preconditions:
        - External Source Provider L2 endpoint.
        - Running UDN VM.

        Steps:
        1. Shut down/remove the external endpoint.
        2. Deploy a VM on the OCP cluster connected to the EVPN CUDN using the exact same IP and MAC.
        3. Initiate TCP traffic between newly deployed VM and the external provider endpoints/another UDN VM.

        Checks:
        - New connections are established after new UDN VM deployment.
        """
