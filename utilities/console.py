import logging
import os
import pty
import shlex
import subprocess

import pexpect
import pexpect.fdpexpect
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutSampler, retry

from utilities.constants import (
    TIMEOUT_5MIN,
    TIMEOUT_10SEC,
    TIMEOUT_30SEC,
    VIRTCTL,
)
from utilities.data_collector import get_data_collector_base_directory

LOGGER = logging.getLogger(__name__)


class Console:
    def __init__(
        self,
        vm: VirtualMachine,
        username: str | None = None,
        password: str | None = None,
        timeout: int = TIMEOUT_30SEC,
        prompt: str | list[str] | None = None,
        kubeconfig: str | None = None,
    ) -> None:
        """
        Connect to VM console

        Args:
            vm: VM resource
            username: VM username
            password: VM password
            timeout: Connection timeout in seconds
            prompt: Shell prompt pattern(s) to expect
            kubeconfig: Path to kubeconfig file for remote cluster access

        Examples:
            from utilities import console
            # Local cluster
            with console.Console(vm=vm) as vmc:
                vmc.sendline('some command')
                vmc.expect('some output')

            # Remote cluster with kubeconfig
            with console.Console(vm=vm, kubeconfig="/path/to/kubeconfig") as vmc:
                vmc.sendline('some command')
                vmc.expect('some output')
        """
        self.vm = vm
        # TODO: `BaseVirtualMachine` does not set cloud-init so the VM is using predefined credentials
        self.username = (
            username or getattr(self.vm, "login_params", {}).get("username") or self.vm.username  # type: ignore[attr-defined]
        )
        self.password = (
            password or getattr(self.vm, "login_params", {}).get("password") or self.vm.password  # type: ignore[attr-defined]
        )
        self.timeout = timeout
        self.child: pexpect.fdpexpect.fdspawn | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self.login_prompt = "login:"
        self.prompt = prompt if prompt else [r"#", r"\$"]
        self.kubeconfig = kubeconfig
        self.cmd = self._generate_cmd()
        self.base_dir = get_data_collector_base_directory()

    @retry(wait_timeout=TIMEOUT_5MIN, sleep=TIMEOUT_10SEC)
    def connect(self):
        LOGGER.info(f"Connect to {self.vm.name} console")
        try:
            self.console_eof_sampler()
            self._connect()
        except Exception:
            LOGGER.exception(f"Failed to connect to {self.vm.name} console.")
            if self.child is not None:
                self.child.close()
            self._terminate_proc()
            raise

        return self.child

    def _connect(self):
        self.child.send("\n\n")
        if self.username:
            self.child.expect(self.login_prompt)
            LOGGER.info(f"{self.vm.name}: Using username {self.username}")
            self.child.sendline(self.username)
            if self.password:
                self.child.expect("Password:")
                LOGGER.info(f"{self.vm.name}: Using password {self.password}")
                self.child.sendline(self.password)

        LOGGER.info(f"{self.vm.name}: waiting for terminal prompt '{self.prompt}'")
        self.child.expect(self.prompt)
        LOGGER.info(f"{self.vm.name}: Got prompt {self.prompt}")

    def disconnect(self):
        if self._proc is not None and self._proc.poll() is not None:
            self.console_eof_sampler()

        try:
            self.child.send("\n\n")
            self.child.expect(self.prompt)
            if self.username:
                self.child.send("exit")
                self.child.send("\n\n")
                self.child.expect("login:")
        finally:
            self.child.close()
            self._terminate_proc()

    def _spawn_console(self) -> pexpect.fdpexpect.fdspawn:
        """
        Creates a pty pair and spawns virtctl via subprocess, returning an fdspawn
        wrapping the master end.

        Uses pty.openpty() + subprocess.Popen instead of pexpect.spawn to avoid
        os.forkpty(), which is deprecated in multi-threaded processes (Python 3.12+).
        """
        master_fd, slave_fd = pty.openpty()
        proc: subprocess.Popen[bytes] | None = None
        try:
            proc = subprocess.Popen(
                shlex.split(self.cmd),
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
            )
            child = pexpect.fdpexpect.fdspawn(fd=master_fd, encoding="utf-8", timeout=self.timeout)
        except OSError, ValueError, pexpect.exceptions.ExceptionPexpect:
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=TIMEOUT_10SEC)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=TIMEOUT_10SEC)
            os.close(master_fd)
            raise
        finally:
            os.close(slave_fd)

        self._proc = proc
        return child

    def _terminate_proc(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.poll() is None:
                    self._proc.terminate()
                self._proc.wait(timeout=TIMEOUT_10SEC)
            except subprocess.TimeoutExpired:
                LOGGER.warning(f"Force killing unresponsive console process for {self.vm.name}")
                self._proc.kill()
                self._proc.wait(timeout=TIMEOUT_10SEC)
            finally:
                self._proc = None

    def console_eof_sampler(self) -> None:
        sampler = TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=self._spawn_console,
            exceptions_dict={pexpect.exceptions.EOF: []},
        )
        for sample in sampler:
            if sample:
                self.child = sample
                self.child.logfile = open(f"{self.base_dir}/{self.vm.name}.pexpect.log", "a")
                break

    def _generate_cmd(self):
        virtctl_str = os.environ.get(VIRTCTL.upper(), VIRTCTL)
        cmd = f"{virtctl_str} console {self.vm.name}"
        if self.vm.namespace:
            cmd += f" -n {self.vm.namespace}"
        if self.kubeconfig:
            cmd += f" --kubeconfig {self.kubeconfig}"
        return cmd

    def __enter__(self):
        """
        Connect to console
        """
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Logout from shell
        """
        self.disconnect()
