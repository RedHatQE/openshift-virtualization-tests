import logging
import shlex

from ocp_resources.virtual_machine_clone import VirtualMachineClone
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import retry

from tests.virt.cluster.vm_cloning.constants import (
    ROOT_DISK_TEST_FILE_STR,
    SECOND_DISK_PATH,
    SECOND_DISK_TEST_FILE_STR,
)
from utilities.constants import TIMEOUT_1SEC, TIMEOUT_10SEC

LOGGER = logging.getLogger(__name__)


class VirtualMachineCloneConditionRunningError(Exception):
    pass


def check_if_files_present_after_cloning(vm):
    LOGGER.info("Check if files present on the disks after cloning")
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[
            # check file on a root
            shlex.split(f"cat {ROOT_DISK_TEST_FILE_STR}"),
            # check on second disk
            shlex.split(f"sudo mount {SECOND_DISK_PATH} /mnt"),
            shlex.split(f"sudo cat {SECOND_DISK_TEST_FILE_STR}"),
        ],
    )


def assert_target_vm_has_new_pvc_disks(source_vm, target_vm):
    def _get_data_volumes_list(vm):
        return [volume["dataVolume"]["name"] for volume in vm.vmi.instance.spec.volumes if "dataVolume" in dict(volume)]

    LOGGER.info("Checking that the target VM created new DataVolumes")
    source_vm_volumes_list = _get_data_volumes_list(vm=source_vm)
    target_vm_volumes_list = _get_data_volumes_list(vm=target_vm)

    assert set(source_vm_volumes_list) != set(target_vm_volumes_list), (
        f"DataVolume on VMs should be unique. \n "
        f"Source VM: {source_vm_volumes_list},\n "
        f"Target VM: {target_vm_volumes_list}"
    )


@retry(
    wait_timeout=TIMEOUT_10SEC,
    sleep=TIMEOUT_1SEC,
    exceptions_dict={VirtualMachineCloneConditionRunningError: []},
)
def wait_cloning_job_source_not_exist_reason(vmc: VirtualMachineClone) -> bool:
    """
    Check if the VirtualMachineClone source does not exist.

    Args:
        vmc (VirtualMachineClone): The VirtualMachineClone resource to check.

    Returns:
        bool: True if the source does not exist, otherwise raises an exception.

    Raises:
        VirtualMachineCloneConditionRunningError: If the ready condition does not
        match the expected source non-existence reason.
    """
    vmc_source = vmc.instance.spec.source
    ready_reason = ""
    expected_reason = f"Source doesnt exist: {vmc_source.kind} {vmc.namespace}/{vmc_source.name}"
    ready_condition = [
        condition
        for condition in vmc.instance.status.conditions
        if condition.type == VirtualMachineClone.Condition.READY
    ]
    if ready_condition and (ready_reason := ready_condition[0].reason) == expected_reason:
        return True
    raise VirtualMachineCloneConditionRunningError(
        f'VMClone ready condition is "{ready_reason}" expected error is"{expected_reason}"'
    )
