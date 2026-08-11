import ipaddress
import json
import logging
from typing import TYPE_CHECKING, Final

from libs.net.vmspec import IpNotFound
from libs.vm.vm import BaseVirtualMachine
from utilities.virt import vm_console_run_commands

if TYPE_CHECKING:
    from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)


def read_guest_interface_ipv4(
    vm: VirtualMachineForTests | BaseVirtualMachine,
    interface_name: str,
    expected_ip: ipaddress.IPv4Address | None = None,
) -> ipaddress.IPv4Interface:
    """Retrieve the IPv4 address and prefix length of an interface from the VM guest OS.

    Args:
        vm: The virtual machine to query.
        interface_name: The name of the network interface (e.g., "eth0").
        expected_ip: When provided, the command filters to this specific host address
            using 'ip addr show to <expected_ip>', which returns output only when
            that address is configured on the interface. Useful when the interface
            may carry multiple addresses.

    Returns:
        IPv4 address with prefix length (e.g., 192.168.1.5/24).

    Raises:
        IpNotFound: If no matching IPv4 address is found or console output cannot be parsed.
    """
    to_filter: Final[str] = f" to {expected_ip}" if expected_ip is not None else ""
    cmd: Final[str] = f"ip -j -4 addr show {interface_name}{to_filter}"

    output = vm_console_run_commands(vm=vm, commands=[cmd], timeout=30)
    LOGGER.info(f"Command {cmd} output: {output[cmd]}")

    try:
        iface_info = json.loads(output[cmd][1])
    except (IndexError, json.JSONDecodeError) as err:
        raise IpNotFound(f"Failed to parse console JSON from VM {vm.name} for '{cmd}': {output[cmd]}") from err

    if iface_info and "addr_info" in iface_info[0]:
        for addr in iface_info[0]["addr_info"]:
            if addr.get("family") == "inet":
                if expected_ip is None or ipaddress.IPv4Address(addr["local"]) == expected_ip:
                    return ipaddress.IPv4Interface(address=f"{addr['local']}/{addr['prefixlen']}")

    raise IpNotFound(
        f"{'No IPv4 address' if expected_ip is None else str(expected_ip)} found on {interface_name} in VM {vm.name}"
    )
