# Permissions and Verbs for set_permissions
from ocp_resources.resource import Resource

from tests.storage.constants import CIRROS_QCOW2_IMG
from utilities.constants import Images

DATAVOLUMES = ["datavolumes"]
DATAVOLUMES_SRC = ["datavolumes/source"]
DATAVOLUMES_AND_DVS_SRC = ["datavolumes", "datavolumes/source"]
PERSISTENT_VOLUME_CLAIMS = ["persistentvolumeclaims"]

CREATE = ["create"]
CREATE_DELETE = ["create", "delete"]
LIST_GET = ["list", "get"]
CREATE_DELETE_LIST_GET = ["create", "delete", "list", "get"]
ALL = ["*"]

PERMISSIONS_SRC = "permissions_src"
PERMISSIONS_DST = "permissions_destination"
VERBS_SRC = "verbs_src"
VERBS_DST = "verbs_dst"

TARGET_DV = "target-dv"

PERMISSIONS_SRC_SA = "perm_src_service_account"
PERMISSIONS_DST_SA = "perm_destination_service_account"
VERBS_SRC_SA = "verbs_src_sa"
VERBS_DST_SA = "verbs_dst_sa"
VM_FOR_TEST = "vm-for-test"
METADATA = "metadata"
SPEC = "spec"

RBAC_AUTHORIZATION_API_GROUP = Resource.ApiGroup.RBAC_AUTHORIZATION_K8S_IO

DV_PARAMS = {
    "dv_name": "source-dv",
    "source": "http",
    "image": CIRROS_QCOW2_IMG,
    "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
}
