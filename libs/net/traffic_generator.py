import logging
from typing import Final

from ocp_resources.pod import Pod
from ocp_utilities.exceptions import CommandExecFailed
from timeout_sampler import TimeoutExpiredError, TimeoutSampler, retry

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

    @property
    def vm(self) -> BaseVirtualMachine:
        return self._vm

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
        self._cmd = f"{_IPERF_BIN} --client {self._server_ip} --time 0 --port {self._server_port} --connect-timeout 0"

    def __enter__(self) -> "Client":
        self._vm.console(
            commands=[f"{self._cmd} &"],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        )
        return self

    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        _stop_process(vm=self._vm, cmd=self._cmd)

    @property
    def vm(self) -> BaseVirtualMachine:
        return self._vm

    def is_running(self) -> bool:
        return _is_process_running(vm=self._vm, cmd=self._cmd)


def _stop_process(vm: BaseVirtualMachine, cmd: str) -> None:
    try:
        vm.console(commands=[f"pkill -f '{cmd}'"], timeout=_DEFAULT_CMD_TIMEOUT_SEC)
    except CommandExecFailed as e:
        LOGGER.warning(str(e))


def _is_process_running(  # type: ignore[return]
    vm: BaseVirtualMachine, cmd: str
) -> bool:
    try:
        for sample in TimeoutSampler(
            wait_timeout=60,
            sleep=5,
            func=vm.console,
            commands=[f"pgrep -fx '{cmd}'"],
            timeout=_DEFAULT_CMD_TIMEOUT_SEC,
        ):
            if sample:
                return True
    except TimeoutExpiredError as e:
        LOGGER.warning(f"Process is not running on VM {vm.name}. Error: {str(e.last_exp)}")
        return False


class PodClient:
    """Represents a TCP client that connects to a server to test network performance.

    Expects pod to have iperf3 container.

    Args:
        pod (Pod): The pod where the client runs.
        server_ip (str): The destination IP address of the server the client connects to.
        server_port (int): The port on which the server listens for connections.
        bind_interface (str): The interface or IP address to bind the client to (optional).
            If not specified, the client will use the default interface.
    """

    def __init__(self, pod: Pod, server_ip: str, server_port: int, bind_interface: str | None = None):
        self._pod = pod
        self._server_ip = server_ip
        self._server_port = server_port
        self._container = _IPERF_BIN
        self._cmd = f"{_IPERF_BIN} --client {self._server_ip} --time 0 --port {self._server_port} --connect-timeout 0"
        self._cmd += f" --bind {bind_interface}" if bind_interface else ""

    def __enter__(self) -> "PodClient":
        # run the command in the background using nohup to ensure it keeps running after the exec session ends
        self._pod.execute(
            command=["sh", "-c", f"nohup {self._cmd} >/tmp/{_IPERF_BIN}.log 2>&1 &"], container=self._container
        )
        self._ensure_is_running()

        return self

    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        self._pod.execute(
            command=["pkill", "-f", self._cmd],
        )

    def is_running(self) -> bool:
        out = self._pod.execute(command=["pgrep", "-f", self._cmd], ignore_rc=True)
        return bool(out.strip())

    @retry(wait_timeout=30, sleep=2, exceptions_dict={ProcessLookupError: []})
    def _ensure_is_running(self) -> bool:
        if self.is_running():
            return True
        raise ProcessLookupError(f"{_IPERF_BIN} client process did not start in the pod {self._pod.name}")


def is_tcp_connection(server: Server, client: Client | PodClient) -> bool:
    return server.is_running() and client.is_running()
