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
    Images,
    StorageClassNames,
)
from utilities.infra import get_latest_os_dict_list
from utilities.os_utils import (
    generate_linux_instance_type_os_matrix,
    generate_os_matrix_dict,
)
from utilities.storage import HppCsiStorageClass

global config

Images.Cirros.RAW_IMG_XZ = "cirros-0.4.0-aarch64-disk.raw.xz"
EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{ARM_64}"


storage_class_matrix = [
    {
        StorageClassNames.TRIDENT_CSI_NFS: {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": False,
            "default": True,
        }
    },
    {
        StorageClassNames.IO2_CSI: {
            "volume_mode": DataVolume.VolumeMode.BLOCK,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": True,
        }
    },
    {HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC: HPP_CAPABILITIES},
]

storage_class_a = StorageClassNames.IO2_CSI
storage_class_b = StorageClassNames.IO2_CSI

os_matrix = {
    AMD_64: {
        "rhel": generate_os_matrix_dict(
            os_name="rhel", supported_operating_systems=["rhel-7-9", "rhel-8-10", "rhel-9-6"], arch=AMD_64
        ),
        "fedora": generate_os_matrix_dict(os_name="fedora", supported_operating_systems=["fedora-43"], arch=AMD_64),
        "centos": generate_os_matrix_dict(
            os_name="centos", supported_operating_systems=["centos-stream-9"], arch=AMD_64
        ),
        "windows": generate_os_matrix_dict(
            os_name="windows",
            supported_operating_systems=["win-10", "win-2016", "win-2019", "win-11", "win-2022", "win-2025"],
            arch=AMD_64,
        ),
    },
    ARM_64: {
        "rhel": generate_os_matrix_dict(os_name="rhel", supported_operating_systems=["rhel-9-6"], arch=ARM_64),
        "fedora": generate_os_matrix_dict(os_name="fedora", supported_operating_systems=["fedora-42"], arch=ARM_64),
        "centos": generate_os_matrix_dict(
            os_name="centos", supported_operating_systems=["centos-stream-9"], arch=ARM_64
        ),
    },
}
latest_os = {
    AMD_64: {
        "rhel": get_latest_os_dict_list(os_list=[os_matrix[AMD_64]["rhel"]]),
        "fedora": get_latest_os_dict_list(os_list=[os_matrix[AMD_64]["fedora"]]),
        "centos": get_latest_os_dict_list(os_list=[os_matrix[AMD_64]["centos"]]),
        "windows": get_latest_os_dict_list(os_list=[os_matrix[AMD_64]["windows"]]),
    },
    ARM_64: {
        "rhel": get_latest_os_dict_list(os_list=[os_matrix[ARM_64]["rhel"]]),
        "fedora": get_latest_os_dict_list(os_list=[os_matrix[ARM_64]["fedora"]]),
        "centos": get_latest_os_dict_list(os_list=[os_matrix[ARM_64]["centos"]]),
    },
}

instance_type_matrix = {
    AMD_64: {
        "rhel": generate_linux_instance_type_os_matrix(
            os_name="rhel", preferences=[RHEL8_PREFERENCE, RHEL9_PREFERENCE, RHEL10_PREFERENCE]
        ),
        "fedora": generate_linux_instance_type_os_matrix(os_name=OS_FLAVOR_FEDORA, preferences=[OS_FLAVOR_FEDORA]),
        "centos": generate_linux_instance_type_os_matrix(
            os_name="centos.stream", preferences=[CENTOS_STREAM9_PREFERENCE, CENTOS_STREAM10_PREFERENCE]
        ),
    },
    ARM_64: {
        "rhel": generate_linux_instance_type_os_matrix(
            os_name="rhel", preferences=[RHEL10_PREFERENCE], arch_suffix=ARM_64
        ),
        "fedora": generate_linux_instance_type_os_matrix(
            os_name=OS_FLAVOR_FEDORA, preferences=[OS_FLAVOR_FEDORA], arch_suffix=ARM_64
        ),
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
