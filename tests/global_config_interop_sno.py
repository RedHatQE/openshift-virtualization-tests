from typing import Any

import pytest_testconfig
from ocp_resources.datavolume import DataVolume

from utilities.constants import (
    ALL_CNV_DAEMONSETS_NO_HPP_CSI,
    ALL_CNV_DEPLOYMENTS_NO_HPP_POOL,
    CNV_PODS_NO_HPP_CSI_HPP_POOL,
)

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

cnv_deployment_matrix = ALL_CNV_DEPLOYMENTS_NO_HPP_POOL
cnv_pod_matrix = CNV_PODS_NO_HPP_CSI_HPP_POOL
cnv_daemonset_matrix = ALL_CNV_DAEMONSETS_NO_HPP_CSI

storage_class_matrix = [
    {
        "sno-storage": {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWO,
            "snapshot": True,
            "online_resize": True,
            "wffc": True,
        }
    },
]

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
