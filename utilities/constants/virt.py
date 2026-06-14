"""VM runtime configuration constants.

Covers virtctl command strings, migration policy values, disk and cloud-init key names,
eviction strategy values, Windows version tags, CPU/memory topology sizing, and
VM-level hardware constants (NUMA, kernel driver, SSH key path).

Not here:
- CNV component deployment/pod name strings → ``components.py``
- Instance type or preference name strings → ``instance_types.py``
- Architecture identifiers (AMD_64, ARM_64, …) → ``architecture.py``
- CPU model exclusion lists → ``cpu_models.py``
- Node labels (CPU model prefix, TSC frequency, worker labels) → ``cluster.py``
- Tekton pipeline/task name strings → ``tekton.py``
"""

VIRTCTL = "virtctl"

LIVE_MIGRATE = "LiveMigrate"
MIGRATION_POLICY_VM_LABEL = {"vm-label": "test-vm"}
ROOTDISK = "rootdisk"
DV_DISK = "dv-disk"

EVICTIONSTRATEGY = "evictionStrategy"
ES_LIVE_MIGRATE_IF_POSSIBLE = "LiveMigrateIfPossible"
ES_NONE = "None"

CLOUD_INIT_DISK_NAME = "cloudinitdisk"
CLOUD_INIT_NO_CLOUD = "cloudInitNoCloud"

VIRTIO = "virtio"
DISK_SERIAL = "D23YZ9W6WA5DJ489"

REGEDIT_PROC_NAME = "regedit.exe"
OS_PROC_NAME = {"linux": "ping", "windows": REGEDIT_PROC_NAME}

STRESS_CPU_MEM_IO_COMMAND = (
    "nohup stress-ng --vm {workers} --vm-bytes {memory} --vm-method all "
    "--verify -t {timeout} -v --hdd 1 --io 1 --vm-keep &> /dev/null &"
)

# Windows versions
WIN_10 = "win10"
WIN_11 = "win11"
WIN_2K25 = "win2k25"
WIN_2K22 = "win2k22"
WIN_2K19 = "win2k19"

HYPERV_FEATURES_LABELS_DOM_XML = [
    "relaxed",
    "vapic",
    "spinlocks",
    "vpindex",
    "synic",
    "stimer",  # synictimer in VM yaml
    "frequencies",
    "ipi",
    "reset",
    "runtime",
    "tlbflush",
    "reenlightenment",
]
HYPERV_FEATURES_LABELS_VM_YAML = HYPERV_FEATURES_LABELS_DOM_XML.copy()
HYPERV_FEATURES_LABELS_VM_YAML[HYPERV_FEATURES_LABELS_VM_YAML.index("stimer")] = "synictimer"


# CPU topology
ONE_CPU_CORE = 1
ONE_CPU_THREAD = 1
TWO_CPU_CORES = 2
TWO_CPU_SOCKETS = 2
TWO_CPU_THREADS = 2
FOUR_CPU_SOCKETS = 4
SIX_CPU_SOCKETS = 6
EIGHT_CPU_SOCKETS = 8
TEN_CPU_SOCKETS = 10

# Memory sizes
FOUR_GI_MEMORY = "4Gi"
FIVE_GI_MEMORY = "5Gi"
SIX_GI_MEMORY = "6Gi"
TEN_GI_MEMORY = "10Gi"
TWELVE_GI_MEMORY = "12Gi"

NODE_HUGE_PAGES_1GI_KEY = "hugepages-1Gi"

# For GPU Passthrough (compute) and SR-IOV VF binding (networking).
KERNEL_DRIVER = "vfio-pci"

CNV_VM_SSH_KEY_PATH = "CNV-SSH-KEY-PATH"
CNV_SUPPLEMENTAL_TEMPLATES_URL = "https://raw.githubusercontent.com/RHsyseng/cnv-supplemental-templates/main/templates"
