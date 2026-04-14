import json
from typing import Final

from kubernetes.dynamic import DynamicClient

from libs.net.traffic_generator import IPERF_SERVER_PORT, TcpServer
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.guest import guest_iface_name
from libs.vm.spec import CloudInitNoCloud, Interface, Multus, Network
from libs.vm.vm import (
    BaseVirtualMachine,
    add_volume_disk,
    cloudinitdisk_storage,
)
from tests.network.libs import cloudinit

BANDWIDTH_SECONDARY_IFACE_NAME: Final[str] = "secondary"
BANDWIDTH_RATE_BPS: Final[int] = 10_000_000  # 10 Mbps

_IPERF_DURATION_SEC: Final[int] = 10
_IPERF_TIMEOUT_BUFFER_SEC: Final[int] = 30  # extra buffer for iperf3 startup and output collection


def active_tcp_connection_output(
    server_vm: BaseVirtualMachine,
    client_vm: BaseVirtualMachine,
    server_ip: str,
    duration: int = _IPERF_DURATION_SEC,
) -> dict:
    """Run a timed iperf3 bidirectional session and return the parsed JSON result.

    Args:
        server_vm: VM running the iperf3 server.
        client_vm: VM running the iperf3 client.
        server_ip: IP address to bind the server and connect the client to.
        duration: Test duration in seconds.

    Returns:
        Parsed iperf3 JSON output dict, e.g.::

            {
                "end": {
                    "sum_received": {"bits_per_second": 9_500_000.0},
                    "sum_received_bidir_reverse": {"bits_per_second": 9_300_000.0},
                }
            }
    """
    with TcpServer(vm=server_vm, port=IPERF_SERVER_PORT, bind_ip=server_ip):
        output = client_vm.console(
            commands=[
                f"iperf3 --client {server_ip} --time {duration} --port {IPERF_SERVER_PORT} --json --bidir 2>/dev/null"
            ],
            timeout=duration + _IPERF_TIMEOUT_BUFFER_SEC,
        )
    try:
        lines = next(iter((output or {}).values()))
    except StopIteration:
        raise ValueError(f"No iperf3 output received for {server_ip}")
    return json.loads("\n".join(lines[1:-1]))


def assert_bidir_throughput_within_limit(
    iperf3_json_report: dict,
    rate_bps: int,
    tolerance: float,
    server_ip: str,
) -> None:
    """Assert that measured bidirectional throughput does not exceed the configured limit.

    Args:
        iperf3_json_report: Parsed iperf3 JSON output dict, e.g.::

            {
                "end": {
                    "sum_received": {"bits_per_second": 9_500_000.0},
                    "sum_received_bidir_reverse": {"bits_per_second": 9_300_000.0},
                }
            }

        rate_bps: Configured bandwidth limit in bits per second.
        tolerance: Multiplier applied to the rate limit (e.g. 1.1 for 10% tolerance).
        server_ip: Server IP address used in the test session (for error messages).
    """
    for direction, key in [("ingress", "sum_received"), ("egress", "sum_received_bidir_reverse")]:
        throughput_bps = iperf3_json_report["end"][key]["bits_per_second"]
        assert throughput_bps <= rate_bps * tolerance, (
            f"Measured {direction} throughput {throughput_bps:.0f} bps exceeds "
            f"configured limit {rate_bps} bps for {server_ip}"
        )


def secondary_network_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    nad_name: str,
    secondary_iface_name: str,
    secondary_iface_addresses: list[str],
    ipv4_supported: bool,
    ipv6_supported: bool,
) -> BaseVirtualMachine:
    """Create a Fedora VM with a masquerade primary interface and a secondary Linux bridge interface.

    Args:
        namespace: Namespace to deploy the VM in.
        name: VM name.
        client: Kubernetes dynamic client.
        nad_name: NetworkAttachmentDefinition name for the secondary interface.
        secondary_iface_name: Name of the secondary network interface in the VM spec.
        secondary_iface_addresses: CIDR addresses to assign to the secondary interface via cloud-init.
        ipv4_supported: Whether IPv4 is supported on the cluster.
        ipv6_supported: Whether IPv6 is supported on the cluster.
    """
    spec = base_vmspec()
    spec.template.spec.domain.devices.interfaces = [  # type: ignore
        Interface(name="default", masquerade={}),
        Interface(name=secondary_iface_name, bridge={}),
    ]
    spec.template.spec.networks = [
        Network(name="default", pod={}),
        Network(name=secondary_iface_name, multus=Multus(networkName=nad_name)),
    ]

    ethernets = {}
    primary = _masquerade_iface_cloud_init(ipv4_supported=ipv4_supported, ipv6_supported=ipv6_supported)
    if primary:
        ethernets[guest_iface_name(ordinal=1)] = primary
    ethernets[guest_iface_name(ordinal=2)] = cloudinit.EthernetDevice(addresses=secondary_iface_addresses)

    userdata = cloudinit.UserData(users=[])
    disk, volume = cloudinitdisk_storage(
        data=CloudInitNoCloud(
            networkData=cloudinit.asyaml(no_cloud=cloudinit.NetworkData(ethernets=ethernets)),
            userData=cloudinit.format_cloud_config(userdata=userdata),
        )
    )
    spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=volume, disk=disk)
    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)


def _masquerade_iface_cloud_init(
    ipv4_supported: bool,
    ipv6_supported: bool,
) -> cloudinit.EthernetDevice | None:
    """Return cloud-init ethernet config for a masquerade (primary) interface.

    Args:
        ipv4_supported: Whether IPv4 is supported on the cluster.
        ipv6_supported: Whether IPv6 is supported on the cluster.

    Returns:
        EthernetDevice with static IPv6 and optional DHCP4, or None if IPv6 is not supported.
    """
    if not ipv6_supported:
        return None
    return cloudinit.EthernetDevice(
        addresses=["fd10:0:2::2/120"],
        gateway6="fd10:0:2::1",
        dhcp4=ipv4_supported,
        dhcp6=False,
    )
