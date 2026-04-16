"""Helpers for OVN localnet migration stuntime tests."""

from __future__ import annotations

import ipaddress
import logging
import re
from collections.abc import Generator
from contextlib import contextmanager
from typing import Final

from libs.vm.vm import BaseVirtualMachine

LOGGER = logging.getLogger(__name__)

STUNTIME_THRESHOLD_SECONDS: Final[float] = 5.0
STUNTIME_PING_LOG_PATH: Final[str] = "/tmp/stuntime-ping.log"
PING_INTERVAL_SECONDS: Final[float] = 0.1


class InsufficientStuntimeDataError(ValueError):
    """Raised when ping log has too few successful replies to compute stuntime."""


def _get_ping_ipv6_flag(destination_ip: str) -> str:
    """Return the ping IPv6 flag based on the IP address version."""
    ip = ipaddress.ip_address(address=destination_ip)
    return " -6" if ip.version == 6 else ""


def compute_stuntime(ping_log: str) -> float:
    """Parse ping summary output and compute stuntime from lost packets.

    Uses the summary line `<tx> packets transmitted, <rx> received` and converts
    packet loss into stuntime using ping interval.

    Args:
        ping_log: Tail output from ping including summary lines.

    Returns:
        float: Stuntime in seconds.

    Raises:
        InsufficientStuntimeDataError: When summary line with transmitted/received is missing.
    """
    summary_match = re.search(r"(\d+)\s+packets transmitted,\s+(\d+)\s+received", ping_log)
    if not summary_match:
        raise InsufficientStuntimeDataError("Insufficient data to compute stuntime (missing ping summary line)")

    transmitted_packets = int(summary_match.group(1))
    received_packets = int(summary_match.group(2))
    lost_packets = transmitted_packets - received_packets
    # Add +1 to account for the gap from last successful reply before loss to first successful reply after recovery
    stuntime = 0.0 if lost_packets == 0 else (lost_packets + 1) * PING_INTERVAL_SECONDS
    LOGGER.info(f"Ping lost={lost_packets}, stuntime={stuntime:.1f}s")
    return stuntime


def _verify_ping_reaches_destination(
    source_vm: BaseVirtualMachine,
    destination_ip: str,
) -> None:
    """Verify network connectivity from source VM to destination IP.

    Args:
        source_vm: The virtual machine from which to initiate the ping.
        destination_ip: The target IP address (IPv4 or IPv6) to ping.
    """
    ping_ipv6_flag = _get_ping_ipv6_flag(destination_ip=destination_ip)
    source_vm.console(
        commands=[f"ping{ping_ipv6_flag} -q -c 3 {destination_ip}"],
        timeout=30,
    )


def _stop_continuous_ping_and_read_log(ping_source_vm: BaseVirtualMachine) -> str:
    """Stop the continuous ping process and retrieve the summary statistics.

    Args:
        ping_source_vm: The virtual machine running the continuous ping.

    Returns:
        str: Ping summary containing packet transmission statistics.
    """
    cmd_pkill = "sudo sh -c 'pkill -SIGINT -x ping || true'"
    cmd_tail = f"sudo tail -n 3 {STUNTIME_PING_LOG_PATH}"
    lines_by_cmd = ping_source_vm.console(
        commands=[cmd_pkill, cmd_tail],
        timeout=120,
    )
    assert lines_by_cmd is not None, "Failed to stop continuous ping and read log"
    ping_log = "\n".join(lines_by_cmd[cmd_tail])
    LOGGER.info(f"Collected ping summary tail from {ping_source_vm.name}")
    return ping_log


class ContinuousPingController:
    """Controller to manage ping lifecycle and retrieve results."""

    def __init__(self, source_vm: BaseVirtualMachine):
        self._source_vm = source_vm
        self._ping_summary: str | None = None

    def stop_and_get_summary(self) -> str:
        """Stop the ping and retrieve the summary.

        Returns:
            str: Ping summary containing packet transmission statistics.
        """
        if self._ping_summary is None:
            self._ping_summary = _stop_continuous_ping_and_read_log(ping_source_vm=self._source_vm)
        return self._ping_summary


@contextmanager
def continuous_ping(
    source_vm: BaseVirtualMachine, destination_ip: str
) -> Generator[ContinuousPingController, None, None]:
    """Context manager for continuous ping monitoring during VM operations.

    Starts a continuous ping process on entry, and stops it on exit,
    guaranteeing cleanup even if exceptions occur.

    Args:
        source_vm: The virtual machine from which to initiate the continuous ping.
        destination_ip: The target IP address (IPv4 or IPv6) to ping continuously.

    Yields:
        ContinuousPingController: Controller with stop_and_get_summary() method.

    Example:
        >>> with continuous_ping(client_vm, server_ip) as ping:
        ...     migrate_vm_and_verify(vm=client_vm)
        ...     measured = compute_stuntime(ping_log=ping.stop_and_get_summary())
    """
    _verify_ping_reaches_destination(source_vm=source_vm, destination_ip=destination_ip)
    ping_ipv6_flag = _get_ping_ipv6_flag(destination_ip=destination_ip)
    source_vm.console(
        commands=[
            f"ping{ping_ipv6_flag} -O -i {PING_INTERVAL_SECONDS} {destination_ip} >{STUNTIME_PING_LOG_PATH} 2>&1 &",
        ],
        timeout=10,
    )
    LOGGER.info(f"Started continuous ping from {source_vm.name} to {destination_ip} (log {STUNTIME_PING_LOG_PATH})")

    controller = ContinuousPingController(source_vm=source_vm)
    try:
        yield controller
    finally:
        controller.stop_and_get_summary()
