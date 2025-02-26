from typing import Any

import pytest_testconfig
from ocp_resources.datavolume import DataVolume

from utilities.constants import (
    ACCESS_MODE,
    ALL_CNV_DAEMONSETS_NO_HPP_CSI,
    ALL_CNV_DEPLOYMENTS_NO_HPP_POOL,
    CNV_PODS_NO_HPP_CSI_HPP_POOL,
    VOLUME_MODE,
    StorageClassNames,
)

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")


RWO = DataVolume.AccessMode.RWO

cnv_deployment_matrix = ALL_CNV_DEPLOYMENTS_NO_HPP_POOL
cnv_pod_matrix = CNV_PODS_NO_HPP_CSI_HPP_POOL
cnv_daemonset_matrix = ALL_CNV_DAEMONSETS_NO_HPP_CSI


storage_class_matrix = [
    {
        StorageClassNames.TOPOLVM: {
            VOLUME_MODE: DataVolume.VolumeMode.BLOCK,
            ACCESS_MODE: RWO,
            "default": True,
        }
    },
]


for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str, int]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
