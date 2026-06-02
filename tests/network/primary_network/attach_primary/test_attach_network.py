"""
Test VM network attachment behavior - RestartRequired condition

Jira: https://redhat.atlassian.net/browse/CNV-87822 # <skip-jira-utils-check>
"""

import pytest

from libs.vm.vm import BaseVirtualMachine
from tests.network.primary_network.attach_primary import libattach


@pytest.mark.polarion("CNV-16026")
@pytest.mark.single_nic
def test_restart_required_when_pod_network_attached(vm_without_pod_interface: BaseVirtualMachine) -> None:
    """
    Test that adding a pod interface to a running VM sets RestartRequired condition.
    Verifies the scenario exposed by a bug.

    Preconditions:
        - Running VM with no interfaces/networks and `autoattachPodInterface: false`

    Steps:
        1. Add a pod interface and network to the VM spec
        2. Check that RestartRequired condition is set in VM status

    Expected:
        - VM reports RestartRequired condition after pod network is added to spec
    """

    libattach.assert_restart_required_condition_not_set(vm=vm_without_pod_interface)
    libattach.add_pod_interface_and_network(vm=vm_without_pod_interface)
    vm_without_pod_interface.wait_for_condition(
        condition="RestartRequired",
        status=vm_without_pod_interface.Condition.Status.TRUE,
        timeout=10,
    )
