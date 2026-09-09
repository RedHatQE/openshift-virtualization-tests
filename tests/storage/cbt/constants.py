"""CBT feature-local constants (backup success only)."""

CBT_TEST_DATA: str = "cbt-backup-test-data-content"
CBT_BOOT_DISK_TEST_DATA_FILE: str = "/tmp/cbt-test-data.txt"
CBT_ENABLED_LABEL: dict[str, str] = {"changedBlockTracking": "true"}
CBT_BACKUP_TYPE_FULL: str = "Full"
CBT_BACKUP_TYPE_INCREMENTAL: str = "Incremental"
CBT_BACKUP_CONDITION_FAILED: str = "Failed"
CBT_DATA_DISK_SIZE: str = "1Gi"
CBT_DATA_DISK_TEST_DATA: str = "cbt-data-disk-test-data-content"
CBT_MULTI_DISK_DATA_DISK_COUNT: int = 2
CBT_BACKUP_CHAIN_INCREMENTAL_COUNT: int = 3
