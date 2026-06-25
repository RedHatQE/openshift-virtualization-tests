"""
SR-IOV VM memory hot-plug tests.

Jira: https://redhat.atlassian.net/browse/CNV-69778 # <skip-jira-utils-check>
"""

import pytest


@pytest.mark.sriov
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
    def test_vmi_status(self):
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
              VM with guest-agent as an info source
        """

    @pytest.mark.polarion("CNV-16279")
    def test_connectivity(self):
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


__test__ = False
