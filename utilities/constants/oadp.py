"""OADP (OpenShift API for Data Protection) test constants.

File names written inside VMs before backup, expected text strings,
backup storage location names, and Velero backup hook annotation keys
used across OADP test scenarios.
"""

FILE_NAME_FOR_BACKUP = "file_before_backup.txt"
TEXT_TO_TEST = "text"
BACKUP_STORAGE_LOCATION = "dpa-1"
SKIP_BACKUP_HOOKS_ANNOTATION = "kubevirt.io/skip-backup-hooks"

# Velero hook annotations injected on virt-launcher when backup hooks are enabled.
# See kubevirt pkg/storage/velero and pkg/storage/pod/annotations/generator.go
VELERO_BACKUP_HOOK_ANNOTATIONS = (
    "pre.hook.backup.velero.io/container",
    "pre.hook.backup.velero.io/command",
    "pre.hook.backup.velero.io/timeout",
    "post.hook.backup.velero.io/container",
    "post.hook.backup.velero.io/command",
)
