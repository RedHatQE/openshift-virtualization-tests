import logging

import pytest

from tests.virt.node.general.utils import (
    get_vm_reboot_count,
)
from utilities.virt import wait_for_running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def reboot_count_before_reset(vm_for_test):
    return get_vm_reboot_count(vm=vm_for_test)


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
        reboot_count_before_reset,
        vm_reset_and_running,
    ):
        assert get_vm_reboot_count(vm=vm_for_test) - reboot_count_before_reset == 1, (
            "Expected 1 reboot entry after VMI reset"
        )
