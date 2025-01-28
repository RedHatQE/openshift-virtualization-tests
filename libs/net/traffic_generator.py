import logging
from typing import Final

from ocp_utilities.exceptions import CommandExecFailed

from libs.vm.vm import BaseVirtualMachine

_DEFAULT_CMD_TIMEOUT_SEC: Final[int] = 10
_IPERF_BIN: Final[str] = "iperf3"


LOGGER = logging.getLogger(__name__)


class Server:
    """
    Represents a server running on a virtual machine for testing network performance.
    Implemented with iperf3

    Args:
        vm (BaseVirtualMachine): The virtual machine where the server runs.
        port (int): The port on which the server listens for client connections.
    """

    def __init__(
        self,
        vm: BaseVirtualMachine,
        port: int,
    ):
        self._vm = vm
        self._port = port
        self._cmd = f"{_IPERF_BIN} --server --port {self._port} --one-off"

    def __enter__(self) -> "Server":
        self._vm.console(
            commands=[f"{self._cmd} &"],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        return self

    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        _stop_process(vm=self._vm, cmd=self._cmd)

    def is_running(self) -> bool:
        return _is_process_running(vm=self._vm, cmd=self._cmd)


class Client:
    """
    Represents a client that connects to a server to test network performance.
    Implemented with iperf3

    Args:
        vm (BaseVirtualMachine): The virtual machine where the client runs.
        server_ip (str): The destination IP address of the server the client connects to.
        server_port (int): The port on which the server listens for connections.
    """

    def __init__(
        self,
        vm: BaseVirtualMachine,
        server_ip: str,
        server_port: int,
    ):
        self._vm = vm
        self._server_ip = server_ip
        self._server_port = server_port
        self._cmd = f"{_IPERF_BIN} --client {self._server_ip} --time 0 --port {self._server_port}"

    def __enter__(self) -> "Client":
        self._vm.console(
            commands=[f"{self._cmd} &"],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        return self

    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        _stop_process(vm=self._vm, cmd=self._cmd)

    def is_running(self) -> bool:
        return _is_process_running(vm=self._vm, cmd=self._cmd)


def _stop_process(vm: BaseVirtualMachine, cmd: str) -> None:
    try:
        vm.console(commands=[f"pkill -f '{cmd}'"], timeout=_DEFAULT_CMD_TIMEOUT_SEC)
    except CommandExecFailed as e:
        LOGGER.warning(str(e))


def _is_process_running(vm: BaseVirtualMachine, cmd: str) -> bool:
    try:
        vm.console(
            commands=[f"pgrep -fAx '{cmd}'"],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        return True
    except CommandExecFailed as e:
        LOGGER.info(f"Process is not running on VM {vm.name}. Error: {str(e)}")
        return False


def is_tcp_connection(server: Server, client: Client) -> bool:
    return server.is_running() and client.is_running()
