import ipaddress
import json
import logging
from typing import Final

from libs.net.vmspec import IpNotFound
from libs.vm.vm import BaseVirtualMachine

LOGGER = logging.getLogger(__name__)


def ip_address_annotation(
    network_name: str,
    ip_address: ipaddress.IPv4Interface | ipaddress.IPv6Interface,
) -> dict[str, str]:
    """
    Generate VM annotation for specifying IP address on a network interface.

    Args:
        network_name: The name of the network interface.
        ip_address: The IP address to assign to the VM network interface.

    Returns:
        Dictionary with the kubevirt IP address annotation key and JSON value.
        Example: {"network.kubevirt.io/addresses": '{"default": ["192.168.1.5"]}'}
    """
    ip_addresses_spec = {network_name: [str(ip_address.ip)]}
    return {"network.kubevirt.io/addresses": json.dumps(ip_addresses_spec)}


def read_guest_interface_ipv4(
    vm: BaseVirtualMachine,
    interface_name: str,
) -> ipaddress.IPv4Interface:
    """
    Retrieve the IPv4 address and prefix length of an interface from the VM guest OS.

    Args:
        vm: The virtual machine to query.
        interface_name: The name of the network interface (e.g., "eth0").

    Returns:
        IPv4 address with prefix length (e.g., 192.168.1.5/24).

    Raises:
        RuntimeError: If command execution fails.
        IpNotFound: If no IPv4 address is found on the specified interface.
    """
    cmd: Final[str] = f"ip -j -4 addr show {interface_name}"
    if not (out := vm.console(commands=[cmd], timeout=10)):
        raise RuntimeError(f"Failed to retrieve IP address from {interface_name}")

    LOGGER.info(f"Command {cmd} output: {out}")

    iface_info = json.loads(out[cmd][1])
    if iface_info and "addr_info" in iface_info[0]:
        for addr in iface_info[0]["addr_info"]:
            if addr["family"] == "inet":
                ip_str = addr["local"]
                prefix_len = addr["prefixlen"]
                return ipaddress.IPv4Interface(address=f"{ip_str}/{prefix_len}")

    raise IpNotFound(f"No IPv4 address found on {interface_name}")
