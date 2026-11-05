import contextlib
import ipaddress
import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from typing import Final, Self

from ocp_resources.pod import Pod
from ocp_utilities.exceptions import CommandExecFailed
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from libs.net.ip import filter_link_local_addresses
from libs.net.vmspec import lookup_iface_status, lookup_iface_status_ip
from libs.vm.vm import BaseVirtualMachine

_DEFAULT_CMD_TIMEOUT_SEC: Final[int] = 10
_IPERF_BIN: Final[str] = "iperf3"
IPERF_SERVER_PORT: Final[int] = 5201
ENSURE_RUNNING_TIMEOUT_SEC: Final[int] = 4


LOGGER = logging.getLogger(__name__)


class BaseTcpClient(ABC):
    """Base abstract class for network traffic generator client."""

    def __init__(self, server_ip: str, server_port: int) -> None:
        self._server_ip = server_ip
        self.server_port = server_port
        self._cmd = (
            f"{_IPERF_BIN} --client {self._server_ip} --time 0 --port {self.server_port} "
            f"--connect-timeout 300 --interval 0"
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

    @abstractmethod
    def _connection_failure_message(self) -> str:
        """Message describing the failed readiness."""


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
    ) -> None:
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
        try:
            _wait_until_running(
                is_running=self.is_running,
                timeout_warning=lambda: f"iperf3 server on {self._vm.name} failed to start on port {self._port}.",
            )
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
        return _is_process_running(vm=self._vm, cmd=self._cmd)


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
    ) -> None:
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
            _wait_until_running(is_running=self.is_running, timeout_warning=self._connection_failure_message)
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
        return _is_connection_established(vm=self._vm, server_ip=self._server_ip, server_port=self.server_port)

    def _connection_failure_message(self) -> str:
        return (
            f"iperf3 client on {self._vm.name} has no established connection to "
            f"{self._server_ip}:{self.server_port}. Client output:\n"
            f"{_read_client_output(vm=self._vm, log_path=self._log_path)}"
        )


def _stop_process(vm: BaseVirtualMachine, cmd: str) -> None:
    """Stop the process matching cmd on the VM, tolerating an already-exited process.

    pkill returns non-zero when nothing matched (the common teardown case), so return-code
    validation is skipped; the try/except still surfaces a genuine console failure.
    """
    try:
        vm.console(commands=[f"pkill -f '{cmd}'"], timeout=_DEFAULT_CMD_TIMEOUT_SEC, return_code_validation=False)
    except CommandExecFailed as stop_process_error:
        LOGGER.warning(str(stop_process_error))


def _is_process_running(vm: BaseVirtualMachine, cmd: str) -> bool:
    try:
        vm.console(
            commands=[f"pgrep -fx '{cmd}'"],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        return True
    except CommandExecFailed:
        return False


def _is_connection_established(vm: BaseVirtualMachine, server_ip: str, server_port: int) -> bool:
    """Check whether the client currently holds an established connection to the server.

    Args:
        vm: The virtual machine running the client.
        server_ip: Destination IP address of the server the client connects to.
        server_port: Port on which the server listens for connections.

    Returns:
        True if an established connection to the server currently exists, False otherwise.
    """
    try:
        vm.console(
            commands=[f"{_established_connection_filter(server_ip=server_ip, server_port=server_port)} | grep -q ."],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        return True
    except CommandExecFailed:
        return False


def _read_client_output(vm: BaseVirtualMachine, log_path: str) -> str:
    read_output_cmd = f"cat {log_path}"
    try:
        output = vm.console(commands=[read_output_cmd], timeout=_DEFAULT_CMD_TIMEOUT_SEC)
    except CommandExecFailed as client_output_read_error:
        return f"<unreadable: {client_output_read_error}>"

    return "\n".join(line for line in output[read_output_cmd] if line.strip() and read_output_cmd not in line)


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
        netns (str): Network namespace to run the client in (optional). Defaults to the
            container's default namespace.
    """

    def __init__(
        self,
        pod: Pod,
        server_ip: str,
        server_port: int,
        bind_interface: str | None = None,
        container: str | None = None,
        netns: str | None = None,
    ) -> None:
        super().__init__(server_ip=server_ip, server_port=server_port)
        self._pod = pod
        self._container = container or _IPERF_BIN
        self._cmd += f" --bind {bind_interface}" if bind_interface else ""
        self._netns = netns
        self._log_path = f"/tmp/{_IPERF_BIN}.log"

    def _build_netns_command(self, command: str) -> str:
        return f"ip netns exec {self._netns} {command}" if self._netns else command

    def __enter__(self) -> Self:
        # run the command in the background using nohup to ensure it keeps running after the exec session ends
        self._pod.execute(
            command=["sh", "-c", f"nohup {self._build_netns_command(self._cmd)} >{self._log_path} 2>&1 &"],
            container=self._container,
        )
        try:
            _wait_until_running(is_running=self.is_running, timeout_warning=self._connection_failure_message)
        except TimeoutExpiredError:
            # __exit__ does not run when __enter__ raises, so stop the leftover client here.
            self._stop_client()
            raise

        return self

    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        self._stop_client()

    def is_running(self) -> bool:
        out = self._pod.execute(
            command=[
                "sh",
                "-c",
                self._build_netns_command(
                    _established_connection_filter(server_ip=self._server_ip, server_port=self.server_port)
                ),
            ],
            container=self._container,
            ignore_rc=True,
        )
        return bool(out.strip())

    def _connection_failure_message(self) -> str:
        return (
            f"iperf3 client pod {self._pod.name} has no established connection to "
            f"{self._server_ip}:{self.server_port}. Client output:\n"
            f"{_read_pod_client_output(pod=self._pod, container=self._container, log_path=self._log_path)}"
        )

    def _stop_client(self) -> None:
        # ignore_rc: pkill returns non-zero when the client already exited (the common case).
        self._pod.execute(command=["pkill", "-f", self._cmd], container=self._container, ignore_rc=True)


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


def _established_connection_filter(server_ip: str, server_port: int) -> str:
    """Build the ss query matching an established client-to-server connection.

    ss requires an IPv6 destination literal to be bracketed; IPv4 is used as-is.

    Args:
        server_ip: Destination IP address of the server the client connects to.
        server_port: Port on which the server listens for connections.

    Returns:
        An ss command that prints the established connection, or nothing when none exists.
    """
    dst = f"[{server_ip}]" if ipaddress.ip_address(server_ip).version == 6 else server_ip
    return f"ss -Ht state established '( dport = :{server_port} and dst {dst} )'"


def _read_pod_client_output(pod: Pod, container: str, log_path: str) -> str:
    output = pod.execute(command=["cat", log_path], container=container, ignore_rc=True)
    return output.strip()


def _wait_until_running(is_running: Callable[[], bool], timeout_warning: Callable[[], str]) -> None:
    """Poll is_running until it reports True, logging a warning if it never does.

    Args:
        is_running: Readiness check polled until it returns True.
        timeout_warning: Builds the warning message logged when readiness is not reached in time.

    Raises:
        TimeoutExpiredError: When readiness is not reached within the timeout.
    """
    try:
        for sample in TimeoutSampler(wait_timeout=ENSURE_RUNNING_TIMEOUT_SEC, sleep=2, func=is_running):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.warning(timeout_warning())
        raise
