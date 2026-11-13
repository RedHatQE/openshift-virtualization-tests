import logging
import os
from typing import Any

import pexpect
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutSampler, retry

from utilities.constants.timeouts import TIMEOUT_2MIN, TIMEOUT_5MIN, TIMEOUT_10SEC, TIMEOUT_30SEC
from utilities.constants.virt import VIRTCTL
from utilities.data_collector import get_data_collector_base_directory

LOGGER = logging.getLogger(__name__)

# A trailing space is required. A bare "#" also matches kernel banners such as "#1 SMP".
DEFAULT_SHELL_PROMPT = [r"# ", r"\$ "]


class Console(object):
    def __init__(
        self,
        vm: VirtualMachine,
        username: str | None = None,
        password: str | None = None,
        timeout: int = TIMEOUT_30SEC,
        login_timeout: int = TIMEOUT_2MIN,
        prompt: str | list[str] | None = None,
        kubeconfig: str | None = None,
    ) -> None:
        """
        Connect to VM console

        Args:
            vm: VM resource
            username: VM username
            password: VM password
            timeout: Command timeout in seconds.
            login_timeout: Seconds to wait for the login or an existing shell prompt. Defaults to 2 minutes.
            prompt: Shell prompt regex or regex patterns to expect. Defaults to ``r"# "`` and ``r"\\$ "``.
                A trailing space avoids matching kernel banners such as ``#1 SMP``.
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
        self.login_timeout = login_timeout
        self.child = None
        self.login_prompt = "login:"
        self.prompt = prompt if prompt else list(DEFAULT_SHELL_PROMPT)
        self.kubeconfig = kubeconfig
        self.cmd = self._generate_cmd()
        self.base_dir = get_data_collector_base_directory()

    @retry(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_10SEC,
        exceptions_dict={
            pexpect.exceptions.EOF: [],
            OSError: [],
        },
    )
    def connect(self):
        """
        Open the virtctl console and log in.

        A missing login prompt fails once. Retrying it used to hide a normal boot behind an error.
        EOF and OSError still retry while virtctl console is not up yet.
        """
        LOGGER.info(f"Connect to {self.vm.name} console")
        self.console_eof_sampler(func=pexpect.spawn, command=self.cmd, timeout=self.timeout)

        try:
            self._connect()
        except pexpect.exceptions.ExceptionPexpect, OSError:
            LOGGER.exception(f"Failed to connect to {self.vm.name} console.")
            if self.child is not None:
                self.child.close()
            raise

        return self.child

    def _connect(self):
        self.child.send("\n\n")
        if self.username:
            # Wait for either "login:" or a shell prompt (e.g., "$ " or "# ").
            patterns = [self.login_prompt] + (self.prompt if isinstance(self.prompt, list) else [self.prompt])
            matched_index = self.child.expect(patterns, timeout=self.login_timeout)

            # Index 0 = login prompt, other indices = shell prompt
            if matched_index == 0:
                # Need to login
                LOGGER.info(f"{self.vm.name}: Using username {self.username}")
                self.child.sendline(self.username)
                if self.password:
                    self.child.expect("Password:")
                    LOGGER.info(f"{self.vm.name}: Using password {self.password}")
                    self.child.sendline(self.password)
            else:
                # Already logged in, skip login sequence
                LOGGER.info(f"{self.vm.name}: Already at shell prompt, skipping login")
                return

        LOGGER.info(f"{self.vm.name}: waiting for terminal prompt '{self.prompt}'")
        self.child.expect(self.prompt, timeout=self.login_timeout)
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

    def console_eof_sampler(self, func: Any, command: str, timeout: int) -> None:
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

    def _generate_cmd(self) -> str:
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

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        Logout from shell.

        A disconnect failure must not replace an exception raised in the with-block.
        """
        try:
            self.disconnect()
        except pexpect.exceptions.ExceptionPexpect, OSError:
            if exc_type is None:
                raise
            LOGGER.warning(f"Failed to disconnect from {self.vm.name} console.", exc_info=True)
