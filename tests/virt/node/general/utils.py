import logging
import shlex

from pyhelper_utils.shell import run_ssh_commands

LOGGER = logging.getLogger(__name__)


def get_vm_reboot_count(vm):
    reboot_count = run_ssh_commands(
        host=vm.ssh_exec,
        commands=[shlex.split("last reboot | grep reboot | wc -l")],
    )[0].strip()

    return int(reboot_count)
