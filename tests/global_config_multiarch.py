from typing import Any

from ocp_resources.datavolume import DataVolume

from utilities.constants import (
    AMD_64,
    ARM_64,
    CENTOS_STREAM9_PREFERENCE,
    CENTOS_STREAM10_PREFERENCE,
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    HPP_CAPABILITIES,
    OS_FLAVOR_FEDORA,
    PREFERENCE_STR,
    RHEL8_PREFERENCE,
    RHEL9_PREFERENCE,
    RHEL10_PREFERENCE,
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

os_matrix = {
    AMD_64: {
        "rhel_os_list": ["rhel-7-9", "rhel-8-10", "rhel-9-6"],
        "fedora_os_list": ["fedora-43"],
        "centos_os_list": ["centos-stream-9"],
        "windows_os_list": ["win-10", "win-2016", "win-2019", "win-11", "win-2022", "win-2025"],
        "instance_type_rhel_os_list": [RHEL8_PREFERENCE, RHEL9_PREFERENCE, RHEL10_PREFERENCE],
        "instance_type_fedora_os_list": [OS_FLAVOR_FEDORA],
        "instance_type_centos_os_list": [CENTOS_STREAM9_PREFERENCE, CENTOS_STREAM10_PREFERENCE],
    },
    ARM_64: {
        "rhel_os_list": ["rhel-9-6"],
        "fedora_os_list": ["fedora-42"],
        "centos_os_list": ["centos-stream-9"],
        "instance_type_rhel_os_list": [RHEL10_PREFERENCE],
        "instance_type_fedora_os_list": [OS_FLAVOR_FEDORA],
    },
}


for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
