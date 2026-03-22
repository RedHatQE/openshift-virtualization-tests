"""Helpers for OVN localnet migration stuntime tests."""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Final

from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.connectivity import build_ping_command

LOGGER = logging.getLogger(__name__)

STUNTIME_THRESHOLD_SECONDS: Final[float] = 5.0
STUNTIME_PING_LOG_PATH: Final[str] = "/tmp/stuntime-ping.log"
PING_INTERVAL_SECONDS: Final[float] = 0.1
DEFAULT_COMMAND_TIMEOUT_SECONDS: Final[int] = 10


class InsufficientStuntimeDataError(ValueError):
    """Raised when ping log has too few successful replies to compute stuntime."""


def compute_stuntime(source_vm: BaseVirtualMachine) -> float:
    """Compute stuntime from ping results.

    Args:
        source_vm: The VM running the continuous ping.

    Returns:
        float: Stuntime in seconds.

    Raises:
        InsufficientStuntimeDataError: When summary line with transmitted/received is missing.
    """
    cmd_tail = f"tail -n 3 {STUNTIME_PING_LOG_PATH}"
    result = source_vm.console(commands=[cmd_tail], timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS)
    ping_summary = "\n".join(result[cmd_tail])

    summary_match = re.search(r"(\d+)\s+packets transmitted,\s+(\d+)\s+received", ping_summary)
    if not summary_match:
        raise InsufficientStuntimeDataError(f"Missing ping summary in log (got: {ping_summary})")

    transmitted_packets = int(summary_match.group(1))
    received_packets = int(summary_match.group(2))
    lost_packets = transmitted_packets - received_packets
    # Add +1 to account for the gap from last successful reply before loss to first successful reply after recovery
    stuntime = 0.0 if lost_packets == 0 else (lost_packets + 1) * PING_INTERVAL_SECONDS
    LOGGER.info(f"Ping lost={lost_packets}, stuntime={stuntime:.1f}s")
    return stuntime


class ContinuousPing:
    """Context manager for continuous ping monitoring during VM operations.

    Example:
        >>> with ContinuousPing(source_vm=client_vm, destination_ip=server_ip) as ping:
        ...     migrate_vm_and_verify(vm=client_vm)
        ...     measured = compute_stuntime(source_vm=active_ping.vm)
    """

    def __init__(self, source_vm: BaseVirtualMachine, destination_ip: str):
        """Initialize continuous ping context manager.

        Args:
            source_vm: The virtual machine from which to initiate the continuous ping.
            destination_ip: The target IP address (IPv4 or IPv6) to ping continuously.
        """
        self._vm = source_vm
        self._destination_ip = destination_ip
        self._cmd = self._build_ping_cmd()

    def __enter__(self) -> "ContinuousPing":
        self._verify_ping_reaches_destination()
        self._vm.console(
            commands=[f"{self._cmd} >{STUNTIME_PING_LOG_PATH} 2>&1 &"],
            timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        )
        LOGGER.info(
            f"Started continuous ping from {self._vm.name} to {self._destination_ip} (log {STUNTIME_PING_LOG_PATH})"
        )
        return self

    def __exit__(
        self, _exc_type: type[BaseException] | None, _exc_value: BaseException | None, _traceback: object
    ) -> None:
        self.stop()

    @property
    def vm(self) -> BaseVirtualMachine:
        return self._vm

    def stop(self) -> None:
        # Use SIGINT (not default SIGTERM) to ensure ping flushes statistics summary before exit
        self._vm.console(
            commands=[f"pkill -SIGINT -f '{self._cmd}' || true"],
            timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        )

    def _build_ping_cmd(self) -> str:
        """Build the continuous ping command with necessary flags.

        Returns:
            str: Continuous Ping command string ready to execute.
        """
        ping_ipv6_flag = get_ping_ipv6_flag(destination_ip=self._destination_ip)
        return f"ping{ping_ipv6_flag} -O -i {PING_INTERVAL_SECONDS} {self._destination_ip}"

    def _verify_ping_reaches_destination(self) -> None:
        """Verify network connectivity from source VM to destination IP."""
        self._vm.console(
            commands=[
                build_ping_command(dst_ip=self._destination_ip, count=3, timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS)
            ],
            timeout=15,
        )


def get_ping_ipv6_flag(destination_ip: str) -> str:
    """Return the ping IPv6 flag based on the IP address version."""
    ip = ipaddress.ip_address(address=destination_ip)
    return " -6" if ip.version == 6 else ""
