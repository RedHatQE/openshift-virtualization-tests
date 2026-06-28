"""
SR-IOV VM memory hot-plug tests.

Jira: https://redhat.atlassian.net/browse/CNV-69778 # <skip-jira-utils-check>
"""

from typing import Final

import pytest

from libs.net.ip import filter_link_local_addresses
from libs.net.vmspec import lookup_iface_status
from tests.network.libs.connectivity import poll_tcp_connectivity
from tests.network.sriov.memory_hotplug.lib_helpers import hotplug_memory_and_wait

_HOTPLUG_MEMORY: Final[str] = "3Gi"


@pytest.mark.jira("CNV-91360", run=False)
@pytest.mark.sriov
@pytest.mark.usefixtures("running_sriov_vms")
@pytest.mark.incremental
class TestSriovMemoryHotplug:
    """
    Tests for SR-IOV VM memory hot-plug.

    Preconditions:
        - Running under-test VM with SR-IOV interface, 1Gi initial
          memory, and 4Gi maxGuest configured
        - Running reference VM with SR-IOV interface on the same
          SR-IOV network
    """

    @pytest.mark.polarion("CNV-16278")
    def test_vmi_status(
        self,
        sriov_vm_with_max_guest,
        sriov_network,
    ):
        """
        Test that after memory hot-plug on SR-IOV VM, the VMI status reflects the
        new memory and the SR-IOV interface is present in the VMI status.

        Preconditions:
            - A running under-test VM with an SR-IOV interface, 1Gi initial
              memory, and 4Gi maxGuest configured

        Steps:
            1. Hot-plug memory to 3Gi on the under-test VM

        Expected:
            - VMI status of the under-test VM shows actual guest memory
              increased to 3Gi
            - SR-IOV interface is present in the VMI status of the under-test
              VM with guest-agent and domain as an info source
        """
        hotplug_memory_and_wait(vm=sriov_vm_with_max_guest, memory_guest=_HOTPLUG_MEMORY)
        lookup_iface_status(
            vm=sriov_vm_with_max_guest,
            iface_name=sriov_network.name,
            predicate=lambda iface: all(source in iface["infoSource"] for source in ("domain", "guest-agent")),
        )

    @pytest.mark.polarion("CNV-16279")
    def test_connectivity(
        self,
        subtests,
        sriov_vm_with_max_guest,
        sriov_ref_vm,
        sriov_network,
    ):
        """
        Test that SR-IOV connectivity is preserved after memory hot-plug.

        Preconditions:
            - Under-test VM after memory hot-plug with SR-IOV interface present
            - A running reference VM with an SR-IOV interface on the same
              SR-IOV network

        Steps:
            1. Poll TCP connection from the under-test VM to the reference VM over the SR-IOV interface

        Expected:
            - TCP connectivity between the under-test VM and the reference VM
              over the SR-IOV interface is eventually preserved after memory hotplug
        """
        ref_iface = lookup_iface_status(vm=sriov_ref_vm, iface_name=sriov_network.name)
        under_test_iface = lookup_iface_status(vm=sriov_vm_with_max_guest, iface_name=sriov_network.name)
        for server_ip in filter_link_local_addresses(ip_addresses=ref_iface.ipAddresses):
            with subtests.test(msg=f"IPv{server_ip.version}: {server_ip}"):
                poll_tcp_connectivity(
                    client_vm=sriov_vm_with_max_guest,
                    server_vm=sriov_ref_vm,
                    server_ip=str(server_ip),
                    client_bind_dev=under_test_iface.interfaceName,
                    server_bind_dev=ref_iface.interfaceName,
                )
