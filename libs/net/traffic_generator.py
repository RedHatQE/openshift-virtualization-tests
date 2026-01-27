import contextlib
import logging
from abc import ABC, abstractmethod
from typing import Final, Generator

from ocp_resources.pod import Pod
from ocp_utilities.exceptions import CommandExecFailed
from timeout_sampler import retry

from libs.net.vmspec import lookup_iface_status_ip
from libs.vm.vm import BaseVirtualMachine

_DEFAULT_CMD_TIMEOUT_SEC: Final[int] = 10
_IPERF_BIN: Final[str] = "iperf3"
IPERF_SERVER_PORT: Final[int] = 5201


LOGGER = logging.getLogger(__name__)


class BaseTcpClient(ABC):
    """Base abstract class for network traffic generator client."""

    def __init__(self, server_ip: str, server_port: int):
        self._server_ip = server_ip
        self.server_port = server_port
        self._cmd = f"{_IPERF_BIN} --client {self._server_ip} --time 0 --port {self.server_port} --connect-timeout 300"

    @abstractmethod
    def __enter__(self) -> "BaseTcpClient":
        pass

    @abstractmethod
    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        pass

    @abstractmethod
    def is_running(self) -> bool:
        pass


class TcpServer:
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

    def __enter__(self) -> "TcpServer":
        self._vm.console(
            commands=[f"{self._cmd} &"],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        self._ensure_is_running()

        return self

    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        _stop_process(vm=self._vm, cmd=self._cmd)

    @property
    def vm(self) -> BaseVirtualMachine:
        return self._vm

    def is_running(self) -> bool:
        return _is_process_running(vm=self._vm, cmd=self._cmd)

    @retry(wait_timeout=30, sleep=2, exceptions_dict={})
    def _ensure_is_running(self) -> bool:
        return self.is_running()


class VMTcpClient(BaseTcpClient):
    """Represents a TCP client that connects to a server to test network performance.
    Implemented with iperf3

    Args:
        vm (BaseVirtualMachine): The virtual machine where the client runs.
        server_ip (str): The destination IP address of the server the client connects to.
        server_port (int): The port on which the server listens for connections.
        maximum_segment_size (int): Define explicitly the TCP payload size (in bytes).
                                    Default value is 0 (do not change mss).
    """

    def __init__(
        self,
        vm: BaseVirtualMachine,
        server_ip: str,
        server_port: int,
        maximum_segment_size: int = 0,
    ):
        super().__init__(server_ip=server_ip, server_port=server_port)
        self._vm = vm
        self._cmd += f" --set-mss {maximum_segment_size}" if maximum_segment_size else ""

    def __enter__(self) -> "VMTcpClient":
        self._vm.console(
            commands=[f"{self._cmd} &"],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        self._ensure_is_running()

        return self

    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        _stop_process(vm=self._vm, cmd=self._cmd)

    @property
    def vm(self) -> BaseVirtualMachine:
        return self._vm

    def is_running(self) -> bool:
        return _is_process_running(vm=self._vm, cmd=self._cmd)

    @retry(wait_timeout=30, sleep=2, exceptions_dict={})
    def _ensure_is_running(self) -> bool:
        return self.is_running()


def _stop_process(vm: BaseVirtualMachine, cmd: str) -> None:
    try:
        vm.console(commands=[f"pkill -f '{cmd}'"], timeout=_DEFAULT_CMD_TIMEOUT_SEC)
    except CommandExecFailed as e:
        LOGGER.warning(str(e))


def _is_process_running(vm: BaseVirtualMachine, cmd: str) -> bool:
    try:
        vm.console(
            commands=[f"pgrep -fx '{cmd}'"],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        return True
    except CommandExecFailed:
        return False


class PodTcpClient(BaseTcpClient):
    """Represents a TCP client that connects to a server to test network performance.

    Expects pod to have a container with iperf3.

    Args:
        pod (Pod): The pod where the client runs.
        server_ip (str): The destination IP address of the server the client connects to.
        server_port (int): The port on which the server listens for connections.
        bind_interface (str): The interface or IP address to bind the client to (optional).
            If not specified, the client will use the default interface.
    """

    def __init__(self, pod: Pod, server_ip: str, server_port: int, bind_interface: str | None = None):
        super().__init__(server_ip=server_ip, server_port=server_port)
        self._pod = pod
        self._container = _IPERF_BIN
        self._cmd += f" --bind {bind_interface}" if bind_interface else ""

    def __enter__(self) -> "PodTcpClient":
        # run the command in the background using nohup to ensure it keeps running after the exec session ends
        self._pod.execute(
            command=["sh", "-c", f"nohup {self._cmd} >/tmp/{_IPERF_BIN}.log 2>&1 &"], container=self._container
        )
        self._ensure_is_running()

        return self

    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        self._pod.execute(command=["pkill", "-f", self._cmd], container=self._container)

    def is_running(self) -> bool:
        out = self._pod.execute(command=["pgrep", "-f", self._cmd], container=self._container, ignore_rc=True)
        return bool(out.strip())

    @retry(wait_timeout=30, sleep=2, exceptions_dict={})
    def _ensure_is_running(self) -> bool:
        return self.is_running()


def is_tcp_connection(server: TcpServer, client: BaseTcpClient) -> bool:
    return server.is_running() and client.is_running()


@contextlib.contextmanager
def client_server_active_connection(
    client_vm: BaseVirtualMachine,
    server_vm: BaseVirtualMachine,
    spec_logical_network: str,
    port: int = IPERF_SERVER_PORT,
    maximum_segment_size: int = 0,
    ip_family: int = 4,
) -> Generator[tuple[VMTcpClient, TcpServer], None, None]:
    """Start iperf3 client-server connection with continuous TCP traffic flow.

    Automatically starts an iperf3 server and client, with traffic flowing continuously
    while inside the context. Both processes stop automatically on exit.

    Args:
        client_vm: VM running the iperf3 client (sends traffic).
        server_vm: VM running the iperf3 server (receives traffic).
        spec_logical_network: Network interface name on server VM for IP resolution.
        port: TCP port for iperf3 connection.
        maximum_segment_size: Define explicitly the TCP payload size (in bytes).
                              Use for jumbo frame testing.
                              Default value is 0 (do not change mss).
        ip_family: IP version to use (4 for IPv4, 6 for IPv6). Default is 4.

    Yields:
        tuple[VMTcpClient, TcpServer]: Client and server objects with active traffic flowing.

    Note:
        Traffic runs with infinite duration until context exits.
    """
    with TcpServer(vm=server_vm, port=port) as server:
        with VMTcpClient(
            vm=client_vm,
            server_ip=str(lookup_iface_status_ip(vm=server_vm, iface_name=spec_logical_network, ip_family=ip_family)),
            server_port=port,
            maximum_segment_size=maximum_segment_size,
        ) as client:
            yield client, server
