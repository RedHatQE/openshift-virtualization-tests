import logging
import os

import pexpect
from timeout_sampler import TimeoutSampler

from utilities.constants import (
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    VIRTCTL,
)
from utilities.data_collector import get_data_collector_base_directory

LOGGER = logging.getLogger(__name__)


class Console(object):
    def __init__(self, vm, username=None, password=None, timeout=30, prompt=None):
        """
        Connect to VM console

        Args:
            vm (VirtualMachine): VM resource
            username (str): VM username
            password (str): VM password

        Examples:
            from utilities import console
            with console.Console(vm=vm) as vmc:
                vmc.sendline('some command)
                vmc.expect('some output')
        """
        self.vm = vm
        # TODO: `BaseVirtualMachine` does not set cloud-init so the VM is using predefined credentials
        self.username = username or getattr(self.vm, "login_params", {}).get("username") or self.vm.username
        self.password = password or getattr(self.vm, "login_params", {}).get("password") or self.vm.password
        self.timeout = timeout
        self.child = None
        self.login_prompt = "login:"
        self.prompt = prompt if prompt else [r"\$"]
        self.cmd = self._generate_cmd()
        self.base_dir = get_data_collector_base_directory()

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
        """
        Connect to the VM console and authenticate if credentials are provided.

        Raises:
            pexpect.exceptions.TIMEOUT: If a shell prompt is not reached after all attempts.
        """
        num_attempts = 5
        for _ in range(num_attempts):
            if self._wait_for_prompt_once():
                return
        raise pexpect.exceptions.TIMEOUT(
            f"{self.vm.name}: Timed out waiting for login/prompt after {num_attempts} attempts."
        )

    def _wait_for_prompt_once(self):
        """
        Perform a single interaction cycle with the console to reach a shell prompt.

        Returns:
            bool: True when a shell prompt is detected; False to indicate a retryable state.

        Raises:
            ValueError: If password prompt received but no password is given.
            pexpect.exceptions.EOF: If console connection ends unexpectedly.
        """
        self.child.send("\n\n")
        prompts = self.prompt if isinstance(self.prompt, list) else [self.prompt]

        if not self.username:
            # No username, just wait for prompt
            self.child.expect(prompts, timeout=TIMEOUT_2MIN)
            return True

        patterns = [self.login_prompt, "Password:", *prompts, pexpect.EOF, pexpect.TIMEOUT]
        while True:
            try:
                index = self.child.expect(patterns, timeout=TIMEOUT_2MIN)
            except pexpect.exceptions.TIMEOUT:
                self.child.send("\n")
                return False

            # Normalize possible non-int (e.g., MagicMock in tests)
            if isinstance(index, int):
                index_int = index
            else:
                LOGGER.debug(f"{self.vm.name}: Non-integer expect index {index!r}; treating as TIMEOUT.")
                index_int = len(patterns) - 1  # TIMEOUT index

            eof_index = len(patterns) - 2
            if index_int == 0:
                LOGGER.info(f"{self.vm.name}: Sending username.")
                self.child.sendline(self.username)
                continue
            if index_int == 1:
                if self.password:
                    LOGGER.info(f"{self.vm.name}: Sending password (masked).")
                    self.child.sendline(self.password)
                    continue
                raise ValueError("Password prompt received but no password provided.")
            if 2 <= index_int < 2 + len(prompts):
                LOGGER.info(f"{self.vm.name}: Shell prompt detected.")
                return True
            if index_int == eof_index:
                raise pexpect.exceptions.EOF(f"{self.vm.name}: EOF while waiting for login/prompt.")
            # TIMEOUT or any other retryable state
            self.child.send("\n")
            return False

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
