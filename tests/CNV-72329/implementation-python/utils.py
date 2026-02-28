"""Utility functions for NAD swap tests."""

from utilities.virt import VirtualMachineForTests


def get_vmi_network_nad_name(vm: VirtualMachineForTests, iface_name: str) -> str:
    """Get the NAD name for a network interface from the VMI spec.

    Args:
        vm: The VirtualMachine resource with a running VMI.
        iface_name: The name of the network interface to look up.

    Returns:
        The multus networkName from the VMI spec for the given interface.

    Raises:
        AssertionError: If the interface is not found in VMI network spec.
    """
    for network in vm.vmi.instance.spec.networks:
        if network.name == iface_name:
            return network.multus.networkName
    raise AssertionError(f"Interface '{iface_name}' not found in VMI spec networks")
