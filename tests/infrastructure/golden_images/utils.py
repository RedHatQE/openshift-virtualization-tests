import logging
import re

import pytest
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import OS_FLAVOR_RHEL, TIMEOUT_2MIN, TIMEOUT_5SEC
from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)


def assert_missing_golden_image_pvc(vm):
    def _verify_missing_pvc_in_vm_conditions(_vm, _expected_message):
        conditions = _vm.instance.status.conditions
        if conditions:
            return any([_expected_message in condition["message"] for condition in conditions if condition["message"]])

    expected_message = "VMI does not exist"

    try:
        # Verify VM error on missing source PVC
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
            func=_verify_missing_pvc_in_vm_conditions,
            _vm=vm,
            _expected_message=expected_message,
        ):
            if sample:
                break
    except TimeoutExpiredError:
        LOGGER.error(
            f"VM {vm.name} condition message does not contain '{expected_message}', "
            f"conditions: {vm.instance.status.conditions}"
        )
        raise


def assert_os_version_mismatch_in_vm(vm: VirtualMachineForTests, expected_os: str) -> None:
    vm_os = vm.ssh_exec.os.release_str.lower()
    match = re.match(r"(?P<os_name>[a-z]+)(?:[.-]stream|\.)?(?P<os_ver>[0-9]+)?", expected_os)
    if not match:
        pytest.fail(f"Did not find matching os_name and os_ver for {expected_os}")
    expected_os_name = match.group("os_name")
    expected_os_ver = match.group("os_ver")
    if expected_os_name == OS_FLAVOR_RHEL:
        expected_os_name = "red hat"
    assert re.match(rf"({expected_os_name}).*({expected_os_ver}).*", vm_os), (
        f"Wrong VM OS, expected name: {expected_os_name}, ver: {expected_os_ver}, actual: {vm_os}"
    )
