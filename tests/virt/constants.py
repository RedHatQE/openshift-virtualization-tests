import bitmath

VIRT_PROCESS_MEMORY_LIMITS = {
    "virt-launcher-monitor": bitmath.MiB(25),
    "virt-launcher": bitmath.MiB(100),
    "virtqemud": bitmath.MiB(40),
    "virtlogd": bitmath.MiB(25),
}


STRESS_CPU_MEM_IO_COMMAND = (
    "nohup stress-ng --vm {workers} --vm-bytes {memory} --vm-method all "
    "--verify -t {timeout} -v --hdd 1 --io 1 --vm-keep &> /dev/null &"
)


# ACRQ
ACRQ_TEST = "acrq-test"
ACRQ_NAMESPACE_LABEL = {ACRQ_TEST: ""}


# MigrationPolicy labels
VM_LABEL = {"post-copy-vm": "true"}


# BASH
REMOVE_NEWLINE = 'tr -d "\n"'


class MachineTypesNames:
    pc_q35 = "pc-q35"
    pc_q35_rhel7_6 = f"{pc_q35}-rhel7.6.0"
    pc_q35_rhel8_1 = f"{pc_q35}-rhel8.1.0"
    pc_q35_rhel9_4 = f"{pc_q35}-rhel9.4.0"
    pc_q35_rhel9_6 = f"{pc_q35}-rhel9.6.0"
    pc_q35_rhel7_4 = f"{pc_q35}-rhel7.4.0"
    pc_i440fx = "pc-i440fx"
    pc_i440fx_rhel7_6 = f"{pc_i440fx}-rhel7.6.0"
