import ipaddress
from collections.abc import Callable

from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutExpiredError, retry

from libs.net.cluster import ipv4_supported_cluster, ipv6_supported_cluster
from libs.net.ip import filter_link_local_addresses, have_same_ip_families, random_ipv4_address, random_ipv6_address
from libs.net.traffic_generator import ns_client_server_active_connection
from libs.net.vmspec import IpNotFound, lookup_iface_status_ip
from libs.vm.vm import BaseVirtualMachine


def ip_family_predicate(ip_addresses: list[str]) -> Callable[[dict], bool]:
    """Return a lookup_iface_status predicate that passes once the interface has IPs from all families in ip_addresses.

    Args:
        ip_addresses: CIDR addresses configured on the interface (e.g. from secondary_iface_addresses).
            The predicate checks that the guest-agent-reported IPs cover the same IP families.
    """
    expected = [ipaddress.ip_interface(addr).ip for addr in ip_addresses]
    return lambda iface: (
        "guest-agent" in iface["infoSource"]
        and have_same_ip_families(
            actual_ips=filter_link_local_addresses(ip_addresses=iface.get("ipAddresses", [])),
            expected_ips=expected,
        )
    )


def secondary_iface_addresses(net_seed: int, host_address: int) -> list[str]:
    """Return CIDR addresses for a secondary interface based on the cluster's IP stack.

    Args:
        net_seed: Seed for the IP address generator (determines the subnet).
        host_address: Host part of the IP address.

    Returns:
        List of CIDR addresses — one per IP family supported by the cluster.
    """
    addresses = []
    if ipv4_supported_cluster():
        addresses.append(f"{random_ipv4_address(net_seed=net_seed, host_address=host_address)}/24")
    if ipv6_supported_cluster():
        addresses.append(f"{random_ipv6_address(net_seed=net_seed, host_address=host_address)}/64")
    return addresses


def build_ping_command(dst_ip: str, count: int, timeout: int) -> str:
    """
    Build a ping command string that handles both IPv4 and IPv6 addresses.

    Args:
        dst_ip: Destination IP address to ping.
        count: Number of packets to send.
        timeout: Timeout in seconds.

    Returns:
        str: Ping command string ready to execute.
    """
    ip = ipaddress.ip_address(address=dst_ip)
    ping_ipv6_flag = " -6" if ip.version == 6 else ""
    return f"ping{ping_ipv6_flag} {dst_ip} -c {count} -w {timeout}"


def update_nad_references(vm: BaseVirtualMachine, updates: dict[str, str]) -> None:
    """Patch the VM spec to update multiple secondary network NAD references in a single atomic call.

    Args:
        vm: The virtual machine to update.
        updates: Mapping of interface name to new NAD name.
    """
    networks = vm.instance.spec.template.spec.networks
    for network in networks:
        if network["name"] in updates:
            network["multus"].update({"networkName": updates[network["name"]]})
    ResourceEditor(patches={vm: {"spec": {"template": {"spec": {"networks": networks}}}}}).update()


def assert_tcp_connectivity_ns(
    client_vm: BaseVirtualMachine,
    server_vm: BaseVirtualMachine,
    server_ip: str,
    server_netns: str,
    connection_present: bool = True,
    client_iface_name: str | None = None,
) -> None:
    """Assert TCP connectivity (or its absence) to a server running inside a network namespace.

    The server IP is provided directly — the guest-agent is not consulted, because interfaces
    inside a network namespace are invisible to it.

    Args:
        client_vm: VM initiating the TCP connection.
        server_vm: VM running the iperf3 server inside server_netns.
        server_ip: IP address the server binds to (must be configured inside server_netns).
        server_netns: Network namespace name on server_vm where the server listens.
        connection_present: When True polls until connectivity exists; when False polls until it does not.
        client_iface_name: When set, binds the client to the IP of this interface on client_vm.
    """
    ip_family = ipaddress.ip_address(address=server_ip).version
    client_bind_ip = (
        str(lookup_iface_status_ip(vm=client_vm, iface_name=client_iface_name, ip_family=ip_family))
        if client_iface_name
        else None
    )
    _poll_tcp_connectivity_ns(
        client_vm=client_vm,
        server_vm=server_vm,
        server_ip=server_ip,
        server_netns=server_netns,
        client_bind_ip=client_bind_ip,
        connection_present=connection_present,
    )


@retry(wait_timeout=60, sleep=5, exceptions_dict={})
def _poll_tcp_connectivity_ns(
    client_vm: BaseVirtualMachine,
    server_vm: BaseVirtualMachine,
    server_ip: str,
    server_netns: str,
    client_bind_ip: str | None = None,
    connection_present: bool = True,
) -> bool:
    try:
        with ns_client_server_active_connection(
            client_vm=client_vm,
            server_vm=server_vm,
            server_ip=server_ip,
            server_netns=server_netns,
            client_bind_ip=client_bind_ip,
        ):
            reachable = True
    except TimeoutExpiredError, IpNotFound:
        reachable = False
    return reachable if connection_present else not reachable
