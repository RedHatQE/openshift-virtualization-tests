from utilities.constants import Images, StorageClassNames
from utilities.storage import HppCsiStorageClass

CIRROS_QCOW2_IMG = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"

ADMIN_NAMESPACE_PARAM = {"use_unprivileged_client": False}

HPP_STORAGE_CLASSES = [
    StorageClassNames.HOSTPATH,
    HppCsiStorageClass.Name.HOSTPATH_CSI_LEGACY,
    HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
    HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_BLOCK,
]

REGISTRY_STR = "registry"
INTERNAL_HTTP_CONFIGMAP_NAME = "internal-https-configmap"
HTTPS_CONFIG_MAP_NAME = "https-cert"
HTTP = "http"
HTTPS = "https"
