from typing import Any

from ocp_resources.datavolume import DataVolume

from utilities.constants.architecture import ARM_64
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.instance_types import (
    CENTOS_STREAM10_PREFERENCE,
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    PREFERENCE_STR,
    RHEL10_PREFERENCE,
)
from utilities.constants.storage import (
    HPP_CAPABILITIES,
    StorageClassNames,
)
from utilities.storage import HppCsiStorageClass

global config

EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{ARM_64}"


storage_class_matrix = [
    {
        StorageClassNames.TRIDENT_CSI_NFS: {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": False,
        }
    },
    {
        StorageClassNames.IO2_CSI: {
            "volume_mode": DataVolume.VolumeMode.BLOCK,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": True,
            "default": True,
        }
    },
    {HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC: HPP_CAPABILITIES},
]

storage_class_a = StorageClassNames.IO2_CSI
storage_class_b = StorageClassNames.IO2_CSI

rhel_os_list = ["rhel-9-5", "rhel-9-6"]
fedora_os_list = ["fedora-42"]
centos_os_list = ["centos-stream-9"]

instance_type_rhel_os_list = [RHEL10_PREFERENCE]
instance_type_centos_os_list = [CENTOS_STREAM10_PREFERENCE]
instance_type_fedora_os_list = [OS_FLAVOR_FEDORA]

for _dir in dir():
    if not config:
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]
