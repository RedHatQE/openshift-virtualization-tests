import ipaddress
import json


def ip_address_annotation(
    network_name: str,
    ip_address: ipaddress.IPv4Interface | ipaddress.IPv6Interface,
) -> dict[str, str]:
    """Generate VM annotation for specifying IP address on a network interface.

    Args:
        network_name: The name of the network interface.
        ip_address: The IP address to assign to the VM network interface.

    Returns:
        Dictionary with the kubevirt IP address annotation key and JSON value.
        Example: {"network.kubevirt.io/addresses": '{"default": ["192.168.1.5"]}'}
    """
    ip_addresses_spec = {network_name: [str(ip_address.ip)]}
    return {"network.kubevirt.io/addresses": json.dumps(ip_addresses_spec)}
