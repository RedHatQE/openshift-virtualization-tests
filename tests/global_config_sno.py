from typing import Any

import pytest_testconfig
from ocp_resources.datavolume import DataVolume

from utilities.constants import StorageClassNames
from utilities.storage import HppCsiStorageClass

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")


ACCESS_MODE = "access_mode"
VOLUME_MODE = "volume_mode"
FILESYSTEM = DataVolume.VolumeMode.FILE
RWO = DataVolume.AccessMode.RWO


HPP_VOLUME_MODE_ACCESS_MODE = {
    VOLUME_MODE: FILESYSTEM,
    ACCESS_MODE: RWO,
}

new_hpp_storage_class_matrix = [
    {HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC: HPP_VOLUME_MODE_ACCESS_MODE},
    {HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_BLOCK: HPP_VOLUME_MODE_ACCESS_MODE},
]

topolvm_storage_class_matrix = [
    {
        StorageClassNames.TOPOLVM: {
            VOLUME_MODE: DataVolume.VolumeMode.BLOCK,
            ACCESS_MODE: RWO,
            "default": True,
        }
    },
]

# Configured in conftest.py - contains either new_hpp_storage_class_matrix or topolvm_storage_class_matrix
storage_class_matrix: list[dict[str, Any]] = []

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str, int]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
