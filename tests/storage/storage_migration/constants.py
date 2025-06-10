FILE_BEFORE_STORAGE_MIGRATION = "file-before-storage-migration"
CONTENT = "some-content"

STORAGE_CLASS_A = "storage_class_for_storage_migration_a"
STORAGE_CLASS_B = "storage_class_for_storage_migration_b"

NO_STORAGE_CLASS_FAILURE_MESSAGE = (
    f"Test failed: {'{storage_class}'} storage class is not deployed. "
    f"Available storage classes: {'{cluster_storage_classes_names}'}. "
    "Ensure the correct storage_class_for_storage_migration is set in the global_config, "
    "or override it with the pytest params: "
    f"--tc={STORAGE_CLASS_A}:<storage_class_name> "
    f"--tc={STORAGE_CLASS_B}:<storage_class_name>"
)
