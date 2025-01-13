import logging
import shlex

from pyhelper_utils.shell import run_ssh_commands

from tests.virt.cluster.vm_cloning.constants import (
    ROOT_DISK_TEST_FILE_STR,
    SECOND_DISK_PATH,
    SECOND_DISK_TEST_FILE_STR,
)

LOGGER = logging.getLogger(__name__)


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
