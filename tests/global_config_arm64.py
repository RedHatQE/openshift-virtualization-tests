import os
from typing import Any

import pytest_testconfig
from ocp_resources.template import Template

from utilities.constants import (
    ARM_64,
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    FLAVOR_STR,
    PREFERENCE_STR,
    Images,
)
from utilities.infra import get_latest_os_dict_list

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

Images.Cirros.RAW_IMG_XZ = "cirros-0.4.0-aarch64-disk.raw.xz"
EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{ARM_64}"

IMAGE_NAME_STR = "image_name"
IMAGE_PATH_STR = "image_path"
DV_SIZE_STR = "dv_size"
TEMPLATE_LABELS_STR = "template_labels"
OS_STR = "os"
WORKLOAD_STR = "workload"
LATEST_RELEASE_STR = "latest_released"
OS_VERSION_STR = "os_version"

rhel_os_matrix = [
    {
        "rhel-9-5": {
            OS_VERSION_STR: "9.5",
            IMAGE_NAME_STR: Images.Rhel.RHEL9_5_ARM64_IMG,
            IMAGE_PATH_STR: os.path.join(Images.Rhel.DIR, Images.Rhel.RHEL9_5_ARM64_IMG),
            DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
            LATEST_RELEASE_STR: True,
            TEMPLATE_LABELS_STR: {
                OS_STR: "rhel9.5",
                WORKLOAD_STR: Template.Workload.SERVER,
                FLAVOR_STR: Template.Flavor.TINY,
            },
        }
    },
]

latest_rhel_os_dict = get_latest_os_dict_list(os_list=[rhel_os_matrix])[0]


for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
