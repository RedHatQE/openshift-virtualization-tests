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
        self.child.send("\n\n")
        prompts = self.prompt if isinstance(self.prompt, list) else [self.prompt]

        if self.username:
            max_attempts = 5
            attempts = 0

            while attempts < max_attempts:
                patterns = [self.login_prompt, "Password:", *prompts, pexpect.EOF, pexpect.TIMEOUT]
                idx = self.child.expect(patterns, timeout=TIMEOUT_2MIN)

                # Normalize possible non-int (e.g., MagicMock in tests) to avoid TypeError on comparisons
                try:
                    idx_int = int(idx)
                except Exception:
                    LOGGER.debug(f"{self.vm.name}: Non-integer expect index {idx!r}; treating as TIMEOUT.")
                    idx_int = len(patterns) - 1  # TIMEOUT index

                eof_idx = len(patterns) - 2

                if idx_int == 0:
                    LOGGER.info(f"{self.vm.name}: Sending username.")
                    self.child.sendline(self.username)
                elif idx_int == 1:
                    if self.password:
                        LOGGER.info(f"{self.vm.name}: Sending password (masked).")
                        self.child.sendline(self.password)
                    else:
                        raise ValueError("Password prompt received but no password provided.")
                elif 2 <= idx_int < 2 + len(prompts):
                    LOGGER.info(f"{self.vm.name}: Shell prompt detected.")
                    break
                elif idx_int == eof_idx:
                    raise pexpect.exceptions.EOF(f"{self.vm.name}: EOF while waiting for login/prompt.")
                else:  # TIMEOUT
                    attempts += 1
                    LOGGER.debug(
                        f"{self.vm.name}: Timeout waiting for login/prompt (attempt {attempts}/{max_attempts})."
                    )
                    self.child.send("\n")
        else:
            # No username, just wait for prompt
            self.child.expect(prompts, timeout=TIMEOUT_2MIN)

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
