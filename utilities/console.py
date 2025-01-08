from __future__ import annotations

import logging
import os
import re

import pexpect
from ocp_utilities.exceptions import CommandExecFailed
from timeout_sampler import TimeoutSampler

from utilities.constants import (
    TIMEOUT_1MIN,
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
                vmc.expecter.sendline('some command)
                vmc.expecter.expect('some output')

                vmc.run_commands("ls -la")
        """
        self.vm = vm
        self.username = username or self.vm.login_params["username"]
        self.password = password or self.vm.login_params["password"]
        self.timeout = timeout
        self.expecter = None
        self.login_prompt = "login:"
        self.prompt = prompt if prompt else [r"\$"]
        self.cmd = self._generate_cmd()
        self.base_dir = get_data_collector_base_directory()

    def connect(self):
        LOGGER.info(f"Connect to {self.vm.name} console")
        self.console_eof_sampler(func=pexpect.spawn, command=self.cmd, timeout=self.timeout)

        self._connect()

        return self.expecter

    def _connect(self):
        self.expecter.send("\n\n")
        if self.username:
            self.expecter.expect(self.login_prompt, timeout=TIMEOUT_5MIN)
            LOGGER.info(f"{self.vm.name}: Using username {self.username}")
            self.expecter.sendline(self.username)
            if self.password:
                self.expecter.expect("Password:")
                LOGGER.info(f"{self.vm.name}: Using password {self.password}")
                self.expecter.sendline(self.password)

        self.expecter.expect(self.prompt, timeout=150)
        LOGGER.info(f"{self.vm.name}: Got prompt {self.prompt}")

    def disconnect(self):
        if self.expecter.terminated:
            self.console_eof_sampler(func=pexpect.spawn, command=self.cmd, timeout=self.timeout)

        self.expecter.send("\n\n")
        self.expecter.expect(self.prompt)
        if self.username:
            self.expecter.send("exit")
            self.expecter.send("\n\n")
            self.expecter.expect("login:")
        self.expecter.close()

    def force_disconnect(self):
        """
        Method is a workaround for RHEL 7.7.
        For some reason, console may not be logged out successfully in __exit__()
        """
        self.console_eof_sampler(func=pexpect.spawn, command=self.cmd, timeout=self.timeout)
        self.disconnect()

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
                self.expecter = sample
                self.expecter.logfile = open(f"{self.base_dir}/{self.vm.name}.pexpect.log", "a")
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
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Logout from shell
        """
        self.disconnect()

    def run_commands(
        self,
        commands: list[str],
        timeout: int = TIMEOUT_1MIN,
        verify_commands_output: bool = True,
        command_output: bool = False,
    ) -> dict[str, list[str]] | None:
        """
        Run a list of commands inside VM and (if verify_commands_output) check all commands return 0.
        If return code other than 0 then it will break execution and raise exception.

        Args:
            commands (list): List of commands
            timeout (int): Time to wait for the command output
            verify_commands_output (bool): Check commands return 0
            command_output (bool): If selected, returns a dict of command and associated output
        """
        output = {}
        # Source: https://www.tutorialspoint.com/how-can-i-remove-the-ansi-escape-sequences-from-a-string-in-python
        ansi_escape = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")
        for command in commands:
            LOGGER.info(f"Execute {command} on {self.vm.name}")
            self.expecter.sendline(command)
            self.expecter.expect(r".*\$")
            output[command] = ansi_escape.sub("", self.expecter.after).replace("\r", "").split("\n")
            if verify_commands_output:
                self.expecter.sendline("echo rc==$?==")  # This construction rc==$?== is unique. Return code validation
                try:
                    self.expecter.expect("rc==0==", timeout=timeout)  # Expected return code is 0
                except pexpect.exceptions.TIMEOUT:
                    raise CommandExecFailed(output[command])
        return output if command_output else None
