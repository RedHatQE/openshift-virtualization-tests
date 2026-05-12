from functools import lru_cache
from typing import TYPE_CHECKING

from pytest_testconfig import config as py_config

from utilities.constants import ArchImages, Images, StorageClassNames
from utilities.storage import HppCsiStorageClass

if TYPE_CHECKING:
    QUAY_FEDORA_CONTAINER_IMAGE: str

CIRROS_QCOW2_IMG = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
ALPINE_QCOW2_IMG = f"{Images.Alpine.DIR}/{Images.Alpine.QCOW2_IMG_VERSIONED}"

ADMIN_NAMESPACE_PARAM = {"use_unprivileged_client": False}

HPP_STORAGE_CLASSES = [
    StorageClassNames.HOSTPATH,
    HppCsiStorageClass.Name.HOSTPATH_CSI_LEGACY,
    HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
    HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_BLOCK,
]

INTERNAL_HTTP_CONFIGMAP_NAME = "internal-https-configmap"
HTTPS_CONFIG_MAP_NAME = "https-cert"
HTTP = "http"
HTTPS = "https"

TEST_FILE_NAME = "test-file.txt"
TEST_FILE_CONTENT = "test-content"


@lru_cache(maxsize=1)
def _get_quay_fedora_container_image() -> str:
    """Get architecture-specific Fedora container image URL."""
    return f"docker://{getattr(ArchImages, py_config['cpu_arch'].upper()).Fedora.FEDORA_CONTAINER_IMAGE}"


def __getattr__(name: str) -> str:
    if name == "QUAY_FEDORA_CONTAINER_IMAGE":
        return _get_quay_fedora_container_image()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
