"""CBT feature-local constants."""

from utilities.constants.images import OS_FLAVOR_RHEL
from utilities.constants.instance_types import RHEL9_PREFERENCE, U1_SMALL

CBT_TEST_DATA: str = "cbt-backup-test-data-content"
CBT_INSTANCE_TYPE_NAME: str = U1_SMALL
CBT_PREFERENCE_NAME: str = RHEL9_PREFERENCE
CBT_OS_FLAVOR: str = OS_FLAVOR_RHEL
# On the root filesystem. /tmp may be tmpfs and would be empty after the restored VM boots.
CBT_BOOT_DISK_TEST_DATA_FILE: str = "/var/tmp/cbt-test-data.txt"
CBT_ENABLED_LABEL: dict[str, str] = {"changedBlockTracking": "true"}
CBT_BACKUP_TYPE_FULL: str = "Full"
CBT_BACKUP_TYPE_INCREMENTAL: str = "Incremental"
CBT_BACKUP_CONDITION_FAILED: str = "Failed"
CBT_DATA_DISK_SIZE: str = "1Gi"
CBT_DATA_DISK_TEST_DATA: str = "cbt-data-disk-test-data-content"
CBT_MULTI_DISK_DATA_DISK_COUNT: int = 2
CBT_BACKUP_CHAIN_INCREMENTAL_COUNT: int = 3
CBT_FILESYSTEM_RESTORE_HEADROOM_GIB: int = 1
CBT_BACKUP_DIR: str = "/backup"
CBT_TARGET_VOLUME_NAME: str = "target-disk"
CBT_TARGET_MOUNT_PATH: str = "/target"
CBT_TARGET_DEVICE_PATH: str = "/dev/target-disk"
CBT_BACKUP_PVC_VOLUME_NAME: str = "backup-src"
