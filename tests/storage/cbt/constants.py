"""CBT feature-local constants (backup success only)."""

CBT_TEST_DATA: str = "cbt-backup-test-data-content"
CBT_INCREMENTAL_TEST_DATA: str = "cbt-incremental-backup-test-data"
CBT_BOOT_DISK_TEST_DATA_FILE: str = "/tmp/cbt-test-data.txt"
CBT_INCREMENTAL_TEST_DATA_FILE: str = "/tmp/cbt-incremental-test-data.txt"
CBT_ENABLED_LABEL: dict[str, str] = {"changedBlockTracking": "true"}
CBT_BACKUP_TYPE_FULL: str = "Full"
CBT_BACKUP_TYPE_INCREMENTAL: str = "Incremental"
CBT_BACKUP_CONDITION_FAILED: str = "Failed"
