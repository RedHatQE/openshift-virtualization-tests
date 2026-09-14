"""Constants for file-level restore tests."""

from utilities.constants.namespaces import NamespacesNames

FILE_RESTORE_OPERATOR_NAMESPACE = NamespacesNames.OPENSHIFT_CNV
FILE_RESTORE_SSH_CONFIGMAP_NAME = "vm-file-restore-operator-ssh"
FILE_RESTORE_OPERATOR_DEPLOYMENT_NAME = "vm-file-restore-operator-controller-manager"

CONFIGMAP_SSH_PUBLIC_KEY = "ssh-publickey"
CONFIGMAP_LINUX_HELPERS_TAR = "linux-helpers.tar"
CONFIGMAP_WINDOWS_HELPERS_TAR = "windows-helpers.tar"

LINUX_SETUP_SCRIPT = "setup.sh"
LINUX_FILERESTORE_SCRIPT = "filerestore.sh"
WINDOWS_SETUP_SCRIPT = "setup.bat"
WINDOWS_FILERESTORE_SCRIPT = "filerestore.bat"
WINDOWS_HELPER_STAGE_DIRECTORY = r"C:\filerestore-helpers"
OPERATOR_SSH_PUBLIC_KEY_FILE_NAME = "operator-ssh-public-key"

LINUX_DATA_DISK_MOUNT_PATH = "/mnt/data"
LINUX_DATA_DISK_SIZE = "5Gi"
LINUX_RESTORE_TEST_DIRECTORY = "restore-test"
LINUX_TEST_FILE_NAME = "file.txt"
LINUX_TEST_FILE_CONTENT = "file-restore-test-content"

WINDOWS_DATA_DISK_LETTER = "E"
WINDOWS_DATA_DISK_SIZE = "5Gi"
WINDOWS_RESTORE_TEST_DIRECTORY = "restore-test"
# Windows sourcePath must be the full original guest path; filerestore restores back to it.
WINDOWS_TEST_FILE_NAME = "file.txt"
WINDOWS_TEST_FILE_CONTENT = "windows-file-restore-test-content"
WINDOWS_DRIVE_ROOT_FILE_NAME = "drive-root-file.txt"
WINDOWS_DRIVE_ROOT_FILE_CONTENT = "windows-drive-root-restore-content"
WINDOWS_MULTI_FILE_COUNT = 3

RESTORE_VOLUME_SUFFIX = "-restore"

LINUX_VENDOR_RESTORE_CR_NAME = "flr-vendor-workflow"
WINDOWS_FILE_COUNT_RESTORE_CR_NAME = "flr-win-count"
WINDOWS_ACL_PVC_RESTORE_CR_NAME = "flr-win-acl-pvc"
WINDOWS_ACL_SNAPSHOT_RESTORE_CR_NAME = "flr-win-acl-snap"
WINDOWS_DRIVE_ROOT_RESTORE_CR_NAME = "flr-win-drive-root"
