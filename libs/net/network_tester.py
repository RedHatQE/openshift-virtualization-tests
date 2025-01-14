from __future__ import annotations

import logging
from typing import Final

from ocp_utilities.exceptions import CommandExecFailed

from libs.vm.vm import BaseVirtualMachine

_DEFAULT_CMD_TIMEOUT_SEC: Final[int] = 10
_IPERF_BIN: Final[str] = "iperf3"


class Protocol:
    TCP: Final[str] = "TCP"
    UDP: Final[str] = "UDP"


LOGGER = logging.getLogger(__name__)


class Server:
    def __init__(
        self,
        vm: BaseVirtualMachine,
        use_one_off: bool,
        port: str,
    ):
        self.vm = vm
        self.use_one_off = use_one_off
        self.port = port
        self._cmd = f"{_IPERF_BIN} -s -D -p {self.port} {'-1' if self.use_one_off else ''}"

    def start(self) -> None:
        try:
            self.vm.console(
                commands=[self._cmd],
                timeout=_DEFAULT_CMD_TIMEOUT_SEC,
            )
            LOGGER.info(f"Server started successfully on VM {self.vm.name}.")
        except CommandExecFailed as e:
            LOGGER.error(f"Failed to start the server on VM {self.vm.name}: {e}")
            raise

    def get_pid(self) -> str:
        get_pid_cmd = f"sudo pgrep -ofA '{self._cmd}'"
        try:
            output = self.vm.console(commands=[get_pid_cmd], timeout=_DEFAULT_CMD_TIMEOUT_SEC)
            if output and get_pid_cmd in output and isinstance(output[get_pid_cmd], list):
                try:
                    return output[get_pid_cmd][-2]  # The second-to-last item is the actual cmd output
                except IndexError:
                    return ""
            return ""
        except CommandExecFailed as e:
            LOGGER.warning(f"Failed to execute command '{get_pid_cmd}' on VM {self.vm}: {str(e)}")
            return ""

    def stop(self) -> None:
        pid = self.get_pid()
        try:
            if pid:
                self.vm.console(commands=[f"sudo kill {pid}"], timeout=_DEFAULT_CMD_TIMEOUT_SEC)
        except CommandExecFailed as e:
            LOGGER.error(f"Failed to stop process with PID {pid} on VM {self.vm.name}: {str(e)}")


class Client:
    def __init__(
        self,
        vm: BaseVirtualMachine,
        dst_ip: str,
        port: str,
        time: str,
        protocol: str,
    ):
        self.vm = vm
        self.dst_ip = dst_ip
        self.port = port
        self.client_time = time
        self.protocol = self._validate_protocol(protocol=protocol)
        self._cmd = (
            f"{_IPERF_BIN} -c {self.dst_ip} "
            f"-t {self.client_time} -p {self.port} "
            f"{'-u' if self.protocol == Protocol.UDP else ''}"
        )

    @staticmethod
    def _validate_protocol(protocol: str) -> str:
        valid_protocols = {Protocol.TCP, Protocol.UDP}
        if protocol not in valid_protocols:
            raise ValueError(f"Invalid protocol: {protocol}. Must be one of: {valid_protocols}.")
        return protocol

    def start(self) -> None:
        try:
            self.vm.console(
                commands=[f"{self._cmd} &"],
                timeout=_DEFAULT_CMD_TIMEOUT_SEC,
            )
            LOGGER.info(f"Client started successfully on VM {self.vm.name}.")
        except CommandExecFailed as e:
            LOGGER.error(f"Failed to start the Client on VM {self.vm.name}: {e}")
            raise

    def get_pid(self) -> str:
        get_pid_cmd = f"sudo pgrep -ofA '{self._cmd}'"
        try:
            output = self.vm.console(commands=[get_pid_cmd], timeout=_DEFAULT_CMD_TIMEOUT_SEC)
            if output and get_pid_cmd in output and isinstance(output[get_pid_cmd], list):
                try:
                    return output[get_pid_cmd][-2]  # The second-to-last item is the actual cmd output
                except IndexError:
                    return ""
            return ""
        except CommandExecFailed as e:
            LOGGER.warning(f"Failed to execute command '{get_pid_cmd}' on VM {self.vm}: {str(e)}")
            return ""

    def stop(self) -> None:
        pid = self.get_pid()
        try:
            if pid:
                self.vm.console(commands=[f"sudo kill {pid}"], timeout=_DEFAULT_CMD_TIMEOUT_SEC)
        except CommandExecFailed as e:
            LOGGER.error(f"Failed to stop process with PID {pid} on VM {self.vm.name}: {str(e)}")


class NetworkTester:
    def __init__(
        self,
        src_vm: BaseVirtualMachine,
        dst_vm: BaseVirtualMachine,
        port: str,
        use_one_off: bool,
        dst_ip: str,
        time: str,
        protocol: str,
    ):
        self._server = Server(vm=src_vm, port=port, use_one_off=use_one_off)
        self._client = Client(vm=dst_vm, dst_ip=dst_ip, port=port, time=time, protocol=protocol)

    def __enter__(self) -> NetworkTester:
        self._server.start()
        self._client.start()
        return self

    def __exit__(self, exc_type: BaseException, exc_value: BaseException, traceback: object) -> None:
        self._client.stop()
        self._server.stop()

    def is_established(self) -> bool:
        server_pid = self._server.get_pid()

        if not server_pid:
            LOGGER.error(f"Server process is not running on VM {self._server.vm.name}.")
            return False

        try:
            self._server.vm.console(
                commands=[
                    f"ss -{'t' if self._client.protocol == Protocol.TCP else 'u'} "
                    f"state established '( dport = :{self._server.port} )'"
                ],
                timeout=_DEFAULT_CMD_TIMEOUT_SEC,
            )
            LOGGER.info(f"{self._client.protocol} socket is established for server on VM {self._server.vm.name}.")
            return True
        except CommandExecFailed:
            LOGGER.error(
                f"No established {self._client.protocol} socket found for server on VM {self._server.vm.name}."
            )
            return False
