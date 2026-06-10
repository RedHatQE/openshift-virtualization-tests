"""VM runtime configuration constants.

Covers virtctl command strings, migration policy values, disk and cloud-init key names,
eviction strategy values, Windows version tags, Tekton task/pipeline names, and
CPU model exclusion lists.

Not here:
- CNV component deployment/pod name strings → ``components.py``
- Instance type or preference name strings → ``instance_types.py``
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

# Windows VirtualMachine preferences
WINDOWS_11_PREFERENCE = "windows.11"
WINDOWS_2K22_PREFERENCE = "windows.2k22"

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

# Tekton Tasks and Pipelines
WINDOWS_EFI_INSTALLER_STR = "windows-efi-installer"
WINDOWS_CUSTOMIZE_STR = "windows-customize"
TEKTON_AVAILABLE_PIPELINEREF = [
    WINDOWS_EFI_INSTALLER_STR,
    WINDOWS_CUSTOMIZE_STR,
]

TEKTON_AVAILABLE_TASKS = [
    "modify-data-object",
    "create-vm-from-manifest",
    "wait-for-vmi-status",
    "cleanup-vm",
    "disk-virt-sysprep",
    "disk-virt-customize",
    "modify-windows-iso-file",
    "disk-uploader",
]

EXCLUDED_CPU_MODELS_S390X = [
    # Below are deprecated & usable models, but violate RHEL 9 ALS (min z14) causing guest to crash (disable-wait)
    # Ref: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/automatically_installing_rhel/preparing-a-rhel-installation-on-64-bit-ibm-z_rhel-installer#planning-for-installation-on-ibm-z_preparing-a-rhel-installation-on-64-bit-ibm-z
    "z114",
    "z114-base",
    "z13",
    "z13-base",
    "z13.2",
    "z13.2-base",
    "z13s",
    "z13s-base",
    "z196",
    "z196-base",
    "z196.2",
    "z196.2-base",
    "zBC12",
    "zBC12-base",
    "zEC12",
    "zEC12-base",
    "zEC12.2",
    "zEC12.2-base",
    # Below are usable (non-deprecated) models, but base models doesn't work on RHEL guests
    # unless required features are appended (ex: 'gen15b-base,vx=on,..'),
    "z14ZR1-base",
    "z14.2-base",
    "z14-base",
    "gen15a-base",
    "gen15b-base",
    "gen16a-base",
    "gen16b-base",
    "gen17a-base",
    "gen17b-base",
]
# Opteron - Windows image can't boot
# Penryn - does not support WSL2
EXCLUDED_CPU_MODELS = [*EXCLUDED_CPU_MODELS_S390X, "Opteron", "Penryn"]
# Latest windows can't boot with old cpu models
EXCLUDED_OLD_CPU_MODELS = [*EXCLUDED_CPU_MODELS, "Westmere", "SandyBridge", "Nehalem", "IvyBridge", "Skylake"]
