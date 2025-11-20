import logging
import shlex

import pytest
from pyhelper_utils.shell import run_ssh_commands

from utilities.virt import wait_for_running_vm

LOGGER = logging.getLogger(__name__)


def get_vm_boot_count(vm):
    reboot_count = run_ssh_commands(
        host=vm.ssh_exec,
        commands=[shlex.split("journalctl --list-boots | wc -l")],
    )[0].strip()

    return int(reboot_count)


@pytest.fixture(scope="class")
def boot_count_before_reset(vm_for_test):
    return get_vm_boot_count(vm=vm_for_test)


@pytest.fixture(scope="class")
def vm_reset_and_running(vm_for_test):
    vm_for_test.vmi.reset()
    wait_for_running_vm(vm=vm_for_test)


@pytest.mark.parametrize("vm_for_test", [pytest.param("vm-for-reset-test")], indirect=True)
class TestVMIReset:
    @pytest.mark.polarion("CNV-12373")
    def test_reset_success(
        self,
        vm_for_test,
        boot_count_before_reset,
        vm_reset_and_running,
    ):
        assert get_vm_boot_count(vm=vm_for_test) - boot_count_before_reset == 1, "Expected 1 boot entry after VMI reset"
