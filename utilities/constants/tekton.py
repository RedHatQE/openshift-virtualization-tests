"""Tekton pipeline and task name constants.

Covers available Tekton pipeline refs and task names for Windows VM automation.

Not here:
- WINDOWS_BOOTSOURCE_PIPELINE (a K8s resource name used in ALL_HCO_RELATED_OBJECTS) → ``components.py``
"""

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
