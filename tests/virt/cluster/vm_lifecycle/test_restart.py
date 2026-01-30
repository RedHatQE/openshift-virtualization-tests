"""
VM Lifecycle Tests - Restart Operations
"""

import logging

import pytest

from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
    wait_for_vm_interfaces,
)

pytestmark = pytest.mark.arm64

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def vm_to_restart(unprivileged_client, namespace):
    name = "vm-to-restart"
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.s390x
@pytest.mark.polarion("CNV-1497")
def test_vm_restart(vm_to_restart):
    """
    Test that a VM can complete a full restart cycle (restart, stop, start).

    Markers:
        - arm64

    Preconditions:
        - Running Fedora virtual machine

    Steps:
        1. Restart the VM and wait for completion
        2. Stop the VM and wait for completion
        3. Start the VM and wait for it to become running

    Expected:
        - VM is running and SSH accessible
    """
    LOGGER.info("VM is running: Restarting VM")
    vm_to_restart.restart(wait=True)
    LOGGER.info("VM is running: Stopping VM")
    vm_to_restart.stop(wait=True)
    LOGGER.info("VM is stopped: Starting VM")
    vm_to_restart.start(wait=True)
    vm_to_restart.vmi.wait_until_running()
    wait_for_vm_interfaces(vmi=vm_to_restart.vmi)
    vm_to_restart.ssh_exec.executor().is_connective()
