import logging
import os

import pexpect
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
    ) -> None:
        """
        Connect to VM console

        Args:
            vm: VM resource
            username: VM username
            password: VM password
            timeout: Connection timeout in seconds
            prompt: Shell prompt pattern(s) to expect

        Examples:
            from utilities import console
            with console.Console(vm=vm) as vmc:
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
        self.child = None
        self.login_prompt = "login:"
        self.prompt = prompt if prompt else [r"#", r"\$"]
        self.cmd = self._generate_cmd()
        self.base_dir = get_data_collector_base_directory()

    @retry(wait_timeout=TIMEOUT_5MIN, sleep=TIMEOUT_10SEC)
    def connect(self):
        LOGGER.info(f"Connect to {self.vm.name} console")
        self.console_eof_sampler(func=pexpect.spawn, command=self.cmd, timeout=self.timeout)

        try:
            self._connect()
        except Exception:
            LOGGER.exception(f"Failed to connect to {self.vm.name} console.")
            self.child.close()
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
        if self.child.terminated:
            self.console_eof_sampler(func=pexpect.spawn, command=self.cmd, timeout=self.timeout)

        try:
            self.child.send("\n\n")
            self.child.expect(self.prompt)
            if self.username:
                self.child.send("exit")
                self.child.send("\n\n")
                self.child.expect("login:")
        finally:
            self.child.close()

    def console_eof_sampler(self, func, command, timeout):
        sampler = TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=func,
            exceptions_dict={pexpect.exceptions.EOF: []},
            command=command,
            timeout=timeout,
            encoding="utf-8",
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
