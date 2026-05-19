import logging

from kubernetes.client import ApiException

from libs.vm.vm import BaseVirtualMachine

LOGGER = logging.getLogger(__name__)


def run_vms(vms: tuple[BaseVirtualMachine, ...]) -> tuple[BaseVirtualMachine, ...]:
    """Start all VMs in parallel then wait for each to be ready and agent-connected.

    Args:
        vms: VMs to start.

    Returns:
        The same tuple of VMs, all running with guest agent connected.
    """
    for vm in vms:
        try:
            vm.start()  # type: ignore[no-untyped-call]
        except ApiException as vm_exception:
            if "VM is already running" in vm_exception.body:
                LOGGER.warning(f"VM {vm.name} is already running")
                continue
    for vm in vms:
        vm.wait_for_ready_status(status=True)  # type: ignore[no-untyped-call]
        vm.wait_for_agent_connected()
    return vms
