import logging

from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_2MIN, TIMEOUT_5SEC

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
