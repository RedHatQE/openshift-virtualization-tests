import os
from copy import deepcopy
from typing import Any

import pytest_testconfig
from ocp_resources.datavolume import DataVolume
from ocp_resources.template import Template

from utilities.constants import (
    ARM_64,
    DV_SIZE_STR,
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    FLAVOR_STR,
    HPP_CAPABILITIES,
    IMAGE_NAME_STR,
    IMAGE_PATH_STR,
    LATEST_RELEASE_STR,
    OS_STR,
    OS_VERSION_STR,
    PREFERENCE_STR,
    TEMPLATE_LABELS_STR,
    WORKLOAD_STR,
    Images,
    StorageClassNames,
)
from utilities.infra import get_latest_os_dict_list
from utilities.storage import HppCsiStorageClass

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

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

storage_class_for_storage_migration_a = StorageClassNames.IO2_CSI
storage_class_for_storage_migration_b = StorageClassNames.IO2_CSI

rhel_os_matrix = [
    {
        "rhel-9-5": {
            OS_VERSION_STR: "9.5",
            IMAGE_NAME_STR: Images.Rhel.RHEL9_5_ARM64_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL9_5_ARM64_IMG),
            DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
            TEMPLATE_LABELS_STR: {
                OS_STR: "rhel9.5",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.TINY,
            },
        }
    },
    {
        "rhel-9-6": {
            OS_VERSION_STR: "9.6",
            IMAGE_NAME_STR: Images.Rhel.RHEL9_6_ARM64_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL9_6_ARM64_IMG),
            DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
            LATEST_RELEASE_STR: True,
            TEMPLATE_LABELS_STR: {
                OS_STR: "rhel9.6",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.TINY,
            },
        }
    },
]

latest_rhel_os_dict = get_latest_os_dict_list(os_list=[rhel_os_matrix])[0]

# Modify instance_type_rhel_os_matrix for arm64
instance_type_rhel_os_matrix = deepcopy(config["instance_type_rhel_os_matrix"])  # noqa: F821
for os_matrix_dict in instance_type_rhel_os_matrix:
    for os_params in os_matrix_dict.values():
        os_params[PREFERENCE_STR] += f".{ARM_64}"

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
