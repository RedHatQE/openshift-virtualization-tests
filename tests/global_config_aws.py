from typing import Any

import pytest_testconfig
from ocp_resources.datavolume import DataVolume

from utilities.constants import (
    ALL_CNV_DAEMONSETS_NO_HPP_CSI,
    ALL_CNV_DEPLOYMENTS_NO_HPP_POOL,
    CNV_PODS_NO_HPP_CSI_HPP_POOL,
    Images,
    StorageClassNames,
)

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

cnv_deployment_matrix = ALL_CNV_DEPLOYMENTS_NO_HPP_POOL
cnv_pod_matrix = CNV_PODS_NO_HPP_CSI_HPP_POOL
cnv_daemonset_matrix = ALL_CNV_DAEMONSETS_NO_HPP_CSI

Images.Windows.DEFAULT_DV_SIZE = "75Gi"

storage_class_matrix = [
    {
        StorageClassNames.PORTWORX_CSI_DB_SHARED: {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": False,
        }
    },
    {
        StorageClassNames.TRIDENT_CSI_FSX: {
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
]

storage_class_a = StorageClassNames.IO2_CSI
storage_class_b = StorageClassNames.IO2_CSI

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
