import bitmath

VIRT_PROCESS_MEMORY_LIMITS = {
    "virt-launcher-monitor": bitmath.MiB(25),
    "virt-launcher": bitmath.MiB(100),
    "virtqemud": bitmath.MiB(35),
    "virtlogd": bitmath.MiB(20),
}


STRESS_CPU_MEM_IO_COMMAND = (
    "nohup stress-ng --vm {workers} --vm-bytes {memory} --vm-method all "
    "--verify -t {timeout} -v --hdd 1 --io 1 --vm-keep &> /dev/null &"
)

# AAQ
AAQ_NAMESPACE_LABEL = {"application-aware-quota/enable-gating": ""}

# ACRQ
ACRQ_TEST = "acrq-test"
ACRQ_NAMESPACE_LABEL = {ACRQ_TEST: ""}


# ARQ Hard fields
PODS_STR = "pods"
LIMITS_CPU_STR = "limits.cpu"
LIMITS_MEMORY_STR = "limits.memory"
REQUESTS_CPU_STR = "requests.cpu"
REQUESTS_MEMORY_STR = "requests.memory"
REQUESTS_INSTANCES_VMI_STR = "requests.instances/vmi"
REQUESTS_CPU_VMI_STR = "requests.cpu/vmi"
REQUESTS_MEMORY_VMI_STR = "requests.memory/vmi"

# MigrationPolicy labels
VM_LABEL = {"post-copy-vm": "true"}


# BASH
REMOVE_NEWLINE = 'tr -d "\n"'
