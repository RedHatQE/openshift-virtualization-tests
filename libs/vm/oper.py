import logging

from kubernetes.client import ApiException

from libs.net.vmspec import wait_for_ifaces_status
from libs.vm.vm import BaseVirtualMachine

LOGGER = logging.getLogger(__name__)


def run_vm(
    vm: BaseVirtualMachine,
    ip_addresses_by_spec_net_name: dict[str, list[str]],
) -> BaseVirtualMachine:
    """Start a VM, wait for agent connection, and verify interface IP addresses.

    Args:
        vm: The virtual machine to start.
        ip_addresses_by_spec_net_name: Mapping of spec network name to expected IP addresses.

    Returns:
        The same VM, running with all interfaces reporting expected IPs.
    """
    vm.start(wait=True)
    vm.wait_for_agent_connected()
    wait_for_ifaces_status(vm=vm, ip_addresses_by_spec_net_name=ip_addresses_by_spec_net_name)
    return vm


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
