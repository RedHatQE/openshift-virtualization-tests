from copy import deepcopy

from tests.os_params import WINDOWS_11
from utilities.constants import Images

STRESS_CPU_MEM_IO_COMMAND = (
    "nohup stress-ng --vm {workers} --vm-bytes {memory} --vm-method all "
    "--verify -t {timeout} -v --hdd 1 --io 1 --vm-keep &> /dev/null &"
)


WINDOWS_11_WSL = deepcopy(WINDOWS_11)
WINDOWS_11_WSL["image_path"] = f"{Images.Windows.DIR}/{Images.Windows.WIN11_WSL2_IMG}"


# ACRQ
ACRQ_TEST = "acrq-test"
ACRQ_NAMESPACE_LABEL = {ACRQ_TEST: ""}


# MigrationPolicy labels
WORKLOAD_DISRUPTION_VM_LABEL = {"workload-disruption-vm": "true"}


# BASH
REMOVE_NEWLINE = 'tr -d "\n"'


class MachineTypesNames:
    pc_q35 = "pc-q35"
    pc_q35_rhel7_6 = f"{pc_q35}-rhel7.6.0"
    pc_q35_rhel8_1 = f"{pc_q35}-rhel8.1.0"
    pc_q35_rhel9_4 = f"{pc_q35}-rhel9.4.0"
    pc_q35_rhel9_8 = f"{pc_q35}-rhel9.8.0"
    pc_q35_rhel7_4 = f"{pc_q35}-rhel7.4.0"
    pc_i440fx = "pc-i440fx"
    pc_i440fx_rhel7_6 = f"{pc_i440fx}-rhel7.6.0"
    s390_ccw_virtio = "s390-ccw-virtio"
    s390_ccw_virtio_rhel9_6 = f"{s390_ccw_virtio}-rhel9.6.0"
    s390_ccw_virtio_rhel8_6 = f"{s390_ccw_virtio}-rhel8.6.0"
    s390_ccw_virtio_rhel7_6 = f"{s390_ccw_virtio}-rhel7.6.0"
