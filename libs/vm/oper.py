from libs.net.vmspec import wait_for_ifaces_status
from libs.vm.vm import BaseVirtualMachine


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
