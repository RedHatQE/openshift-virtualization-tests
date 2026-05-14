import json
from typing import Final

from libs.net.traffic_generator import IPERF_SERVER_PORT, TcpServer
from libs.vm.vm import BaseVirtualMachine

BANDWIDTH_SECONDARY_IFACE_NAME: Final[str] = "secondary"
BANDWIDTH_RATE_BPS: Final[int] = 10_000_000  # 10 Mbps

_IPERF_DURATION_SEC: Final[int] = 10
_IPERF_TIMEOUT_BUFFER_SEC: Final[int] = 30  # extra buffer for iperf3 startup and output collection
GUEST_2ND_IFACE_NAME: Final[str] = "eth1"


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
