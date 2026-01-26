"""
IP addresses specification on a VM

Tests are aimed to cover the ability to define at VM definition its primary UDN IP address.

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-network/ip-request.md
"""

__test__ = False

import pytest


class TestVMWithExplicitIPAddressSpecification:
    """
    Tests for VM with an IP address explicitly defined for the primary UDN.

    Markers:
        - IPv4
        - single_nic
        - incremental

    Preconditions:
        - UDN supported namespace.
        - UDN resource for the primary network (with an IP range defined).
        - Base halted under-test VM with a primary UDN network.
        - Base running connectivity reference VM with a primary UDN network.
    """

    @pytest.mark.polarion("CNV-13120")
    def test_vm_is_started_with_successful_connectivity(self):
        """
        Test that a VM with an explicit IP address specified is started successfully and is reachable.

        Preconditions:
            - Stopped under-test VM, with a primary UDN network (no IP address specified).
            - Running connectivity reference VM, with a primary UDN network.
            - IP address to specify on under-test VM.

        Steps:
            1. Set IP address on under-test VM through annotation and cloud-init network-data.
            2. Start the VM and wait for the Ip to be reported on the VMI status.
            3. Establish TCP connectivity from the ref VM to the under-test VM.

        Expected:
            - IP address reported by VMI status and guest OS is the same as the one specified.
            - Verify that the VM is reachable from the ref VM.
        """

    @pytest.mark.polarion("CNV-12582")
    def test_successful_external_connectivity(self):
        """
        Test that a VM with an explicit IP address specified is reaching an external IP address.

        Preconditions:
            - Running under-test VM, with a primary UDN network and an IP address specified
              (through annotation & cloud-init).

        Steps:
            1. Execute a ping command from the under-test VM to the external IP address.

        Expected:
            - Verify that the ping command succeeds with 0% packet loss.
        """

    @pytest.mark.polarion("CNV-12586")
    def test_seamless_in_cluster_connectivity_is_preserved_over_live_migration(self):
        """
        Test that a VM with an explicit IP address specified can preserve connectivity during live migration.

        Preconditions:
            - Running under-test VM, with a primary UDN network and an IP address specified
              (through annotation & cloud-init).
            - Running connectivity reference VM, with a primary UDN network.
            - Established TCP connectivity from the ref VM to the under-test VM.

        Steps:
            1. Migrate the under-test VM (and wait for completion).

        Expected:
            - The initial TCP connection is preserved (no disconnection).
        """

    @pytest.mark.polarion("CNV-12585")
    def test_ip_address_is_preserved_over_power_lifecycle(self):
        """
        Test that a VM with an explicit IP address specified can preserve its IP address over a power lifecycle
        (VM is stopped and started again).

        Preconditions:
            - Running under-test VM, with a primary UDN network and an IP address specified
              (through annotation & cloud-init).
            - The specified IP address on the under-test VM.

        Steps:
            1. Restart the under-test VM (and wait for completion).

        Expected:
            - IP address reported by VMI status and guest OS is the same as the one specified.
        """
