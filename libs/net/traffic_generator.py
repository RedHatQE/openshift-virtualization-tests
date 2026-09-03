import contextlib
import ipaddress
import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Final, Self

from ocp_resources.pod import Pod
from ocp_utilities.exceptions import CommandExecFailed
from timeout_sampler import TimeoutExpiredError, retry

from libs.net.ip import filter_link_local_addresses
from libs.net.vmspec import lookup_iface_status, lookup_iface_status_ip
from libs.vm.vm import BaseVirtualMachine

_DEFAULT_CMD_TIMEOUT_SEC: Final[int] = 10
_IPERF_BIN: Final[str] = "iperf3"
IPERF_SERVER_PORT: Final[int] = 5201


LOGGER = logging.getLogger(__name__)


class BaseTcpClient(ABC):
    """Base abstract class for network traffic generator client."""

    def __init__(self, server_ip: str, server_port: int):
        """Build the base iperf3 client command.

        --connect-timeout is in milliseconds; --interval 0 disables the periodic
        per-second throughput reports.
        """
        self._server_ip = server_ip
        self.server_port = server_port
        self._cmd = (
            f"{_IPERF_BIN} --client {self._server_ip} --time 0 --port {self.server_port} "
            f"--connect-timeout 5000 --interval 0"
        )

    @property
    def server_ip(self) -> str:
        return self._server_ip

    @abstractmethod
    def __enter__(self) -> Self:
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
        bind_ip (str): The IP address to bind the server to (optional).
        bind_dev (str): Guest network device to bind the server socket to via SO_BINDTODEVICE
            (e.g. "eth1"). Forces responses out this interface, bypassing ECMP routing.
    """

    def __init__(
        self,
        vm: BaseVirtualMachine,
        port: int,
        bind_ip: str | None = None,
        bind_dev: str | None = None,
    ):
        self._vm = vm
        self._port = port
        self._cmd = f"{_IPERF_BIN} --server --port {self._port} --one-off"
        self._cmd += f" --bind {bind_ip}" if bind_ip else ""
        self._cmd += f" --bind-dev {bind_dev}" if bind_dev else ""

    def __enter__(self) -> Self:
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
        bind_dev (str): Guest network device to bind the client socket to via SO_BINDTODEVICE
            (e.g. "eth1"). Forces traffic out this interface, bypassing ECMP routing.
    """

    def __init__(
        self,
        vm: BaseVirtualMachine,
        server_ip: str,
        server_port: int,
        maximum_segment_size: int = 0,
        bind_dev: str | None = None,
    ):
        super().__init__(server_ip=server_ip, server_port=server_port)
        self._vm = vm
        self._cmd += f" --bind-dev {bind_dev}" if bind_dev else ""
        self._cmd += f" --set-mss {maximum_segment_size}" if maximum_segment_size else ""
        # Unique per instance so concurrent clients on the same VM never share a log.
        self._log_path = f"/tmp/{_IPERF_BIN}_client_{uuid.uuid4().hex}.log"

    def __enter__(self) -> Self:
        """Start the iperf3 client in the background, capturing its output to a log file.

        stdbuf forces line-buffered output; otherwise iperf3 block-buffers stdout when
        redirected and the connection banner is never flushed. On readiness failure the client
        is stopped here, since __exit__ does not run when __enter__ raises and the client may
        have connected and be generating traffic despite the failed readiness check.
        """
        self._vm.console(
            commands=[f"stdbuf -oL -eL {self._cmd} >{self._log_path} 2>&1 &"],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        try:
            self._ensure_is_running()
        except TimeoutExpiredError:
            _stop_process(vm=self._vm, cmd=self._cmd)
            raise

        return self

    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        _stop_process(vm=self._vm, cmd=self._cmd)

    @property
    def vm(self) -> BaseVirtualMachine:
        return self._vm

    def is_running(self) -> bool:
        return _is_connection_established(
            vm=self._vm, server_ip=self._server_ip, server_port=self.server_port, log_path=self._log_path
        )

    @retry(wait_timeout=30, sleep=2, exceptions_dict={})
    def _ensure_is_running(self) -> bool:
        return self.is_running()


def _stop_process(vm: BaseVirtualMachine, cmd: str) -> None:
    # `|| true` so a process that already exited is not treated as an error.
    try:
        vm.console(commands=[f"pkill -f '{cmd}' || true"], timeout=_DEFAULT_CMD_TIMEOUT_SEC)
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


def _is_connection_established(vm: BaseVirtualMachine, server_ip: str, server_port: int, log_path: str) -> bool:
    """Check whether the client currently holds an established connection to the server.

    Queries the live socket state rather than relying on client-process liveness (a running
    process may still be attempting - or have failed - to connect) or on the client output (a
    past connection banner does not prove the connection is still up after a disruptive event
    such as migration). When no established connection is found, the captured client output is
    logged to ease debugging.

    Args:
        vm: The virtual machine running the client.
        server_ip: Destination IP address of the server the client connects to.
        server_port: Port on which the server listens for connections.
        log_path: Path on the VM holding the iperf3 client output, logged on failure.

    Returns:
        True if an established connection to the server currently exists, False otherwise.
    """
    # ss requires an IPv6 destination literal to be bracketed; IPv4 is used as-is.
    dst = f"[{server_ip}]" if ipaddress.ip_address(server_ip).version == 6 else server_ip
    try:
        vm.console(
            commands=[f"ss -Ht state established '( dport = :{server_port} and dst {dst} )' | grep -q ."],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        return True
    except CommandExecFailed:
        LOGGER.warning(
            f"iperf3 client on {vm.name} has no established connection to {server_ip}:{server_port}. "
            f"Client output:\n{_read_client_output(vm=vm, log_path=log_path)}"
        )
        return False


def _read_client_output(vm: BaseVirtualMachine, log_path: str) -> str:
    """Return the iperf3 client output captured on the VM, or a placeholder when unreadable.

    The captured lines include the echoed command and shell prompt, which are dropped so only
    the iperf3 output remains.
    """
    read_output_cmd = f"cat {log_path}"
    try:
        output = vm.console(commands=[read_output_cmd], timeout=_DEFAULT_CMD_TIMEOUT_SEC)
    except CommandExecFailed as client_output_read_error:
        return f"<unreadable: {client_output_read_error}>"

    return (
        "\n".join(line for line in output[read_output_cmd] if line.strip() and read_output_cmd not in line) or "empty"
    )


class PodTcpClient(BaseTcpClient):
    """Represents a TCP client that connects to a server to test network performance.

    Expects pod to have a container with iperf3.

    Args:
        pod (Pod): The pod where the client runs.
        server_ip (str): The destination IP address of the server the client connects to.
        server_port (int): The port on which the server listens for connections.
        bind_interface (str): The interface or IP address to bind the client to (optional).
            If not specified, the client will use the default interface.
        container (str): Container name to execute commands in.
    """

    def __init__(
        self,
        pod: Pod,
        server_ip: str,
        server_port: int,
        bind_interface: str | None = None,
        container: str | None = None,
    ) -> None:
        super().__init__(server_ip=server_ip, server_port=server_port)
        self._pod = pod
        self._container = container or _IPERF_BIN
        self._cmd += f" --bind {bind_interface}" if bind_interface else ""

    def __enter__(self) -> Self:
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
def active_tcp_connections(
    client_vm: BaseVirtualMachine,
    server_vm: BaseVirtualMachine,
    iface_name: str,
) -> Generator[list[tuple[VMTcpClient, TcpServer]]]:
    """Start iperf3 client-server connections for all IPs on the server's interface.
       The helper assumed the ip addresses are up.

    Args:
        client_vm: VM running the iperf3 client.
        server_vm: VM running the iperf3 server.
        iface_name: Network interface name on the server VM to resolve IPs from.

    Yields:
        List of (VMTcpClient, TcpServer) tuples, one per enabled IP family.
    """
    iface = lookup_iface_status(vm=server_vm, iface_name=iface_name)
    server_ips = [ip for ip in filter_link_local_addresses(ip_addresses=iface.ipAddresses)]
    with contextlib.ExitStack() as stack:
        active_conns = []
        for server_ip in server_ips:
            active_conns.append(
                stack.enter_context(
                    client_server_active_connection(
                        client_vm=client_vm,
                        server_vm=server_vm,
                        spec_logical_network=iface.name,
                        ip_family=server_ip.version,
                    )
                )
            )
        yield active_conns


@contextlib.contextmanager
def client_server_active_connection(
    client_vm: BaseVirtualMachine,
    server_vm: BaseVirtualMachine,
    spec_logical_network: str,
    port: int = IPERF_SERVER_PORT,
    maximum_segment_size: int = 0,
    ip_family: int = 4,
) -> Generator[tuple[VMTcpClient, TcpServer]]:
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
    server_ip = str(lookup_iface_status_ip(vm=server_vm, iface_name=spec_logical_network, ip_family=ip_family))
    with TcpServer(vm=server_vm, port=port, bind_ip=server_ip) as server:
        with VMTcpClient(
            vm=client_vm,
            server_ip=server_ip,
            server_port=port,
            maximum_segment_size=maximum_segment_size,
        ) as client:
            yield client, server
