from pytest_testconfig import py_config

from utilities.constants import ArchImages, Images, StorageClassNames
from utilities.storage import HppCsiStorageClass

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

QUAY_FEDORA_CONTAINER_IMAGE = (
    f"docker://{getattr(ArchImages, py_config['cpu_arch'].upper()).Fedora.FEDORA_CONTAINER_IMAGE}"
)

TEST_FILE_NAME = "test-file.txt"
TEST_FILE_CONTENT = "test-content"
