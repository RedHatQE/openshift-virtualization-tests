from utilities.constants import Images
from utilities.constants.images import ArchImages

NUM_BLANK_DISKS = 3

CIRROS_QCOW2_IMG = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
ALPINE_QCOW2_IMG = f"{Images.Alpine.DIR}/{Images.Alpine.QCOW2_IMG_VERSIONED}"

ADMIN_NAMESPACE_PARAM = {"use_unprivileged_client": False}

INTERNAL_HTTP_CONFIGMAP_NAME = "internal-https-configmap"
HTTPS_CONFIG_MAP_NAME = "https-cert"
HTTP = "http"
HTTPS = "https"

# Import-time constant — resolves to the first arch in OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH.
# On heterogeneous (s390x+arm64) runs this may not match --cpu-arch.
# Use get_fedora_container_image(cpu_arch) for arch-aware selection at test runtime.
QUAY_FEDORA_CONTAINER_IMAGE = f"docker://{Images.Fedora.FEDORA_CONTAINER_IMAGE}"

_ARCH_TO_FEDORA_CONTAINER = {
    "arm64": ArchImages.ARM64.Fedora.FEDORA_CONTAINER_IMAGE,
    "s390x": ArchImages.S390X.Fedora.FEDORA_CONTAINER_IMAGE,
    "amd64": ArchImages.AMD64.Fedora.FEDORA_CONTAINER_IMAGE,
}


def get_fedora_container_image(cpu_arch: str = "") -> str:
    """Return the arch-aware Fedora container image URL for CDI registry imports.

    Falls back to the module-level QUAY_FEDORA_CONTAINER_IMAGE when cpu_arch is
    empty or unrecognised (e.g. non-multiarch single-arch runs where Images is
    already set to the correct arch).
    """
    tag = _ARCH_TO_FEDORA_CONTAINER.get(cpu_arch)
    if tag:
        return f"docker://{tag}"
    return QUAY_FEDORA_CONTAINER_IMAGE


TEST_FILE_NAME = "test-file.txt"
TEST_FILE_CONTENT = "test-content"

NUM_HOTPLUG_DISKS = 3
BLANK_DV_SIZE = "1Gi"

STORAGE_CLASS_A = "storage_class_a"
STORAGE_CLASS_B = "storage_class_b"

NO_STORAGE_CLASS_FAILURE_MESSAGE = (
    f"Test failed: {'{storage_class}'} storage class is not deployed. "
    f"Available storage classes: {'{cluster_storage_classes_names}'}. "
    "Ensure the correct storage_class is set in the global_config, "
    "or override it with the pytest params: "
    f"--tc={STORAGE_CLASS_A}:<storage_class_name> "
    f"--tc={STORAGE_CLASS_B}:<storage_class_name>"
)
