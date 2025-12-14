from typing import Any

import pytest_testconfig
from ocp_resources.datavolume import DataVolume

from utilities.constants import ACCESS_MODE, VOLUME_MODE, StorageClassNames

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")


RWO = DataVolume.AccessMode.RWO


storage_class_matrix = [
    {
        StorageClassNames.TOPOLVM: {
            VOLUME_MODE: DataVolume.VolumeMode.BLOCK,
            ACCESS_MODE: RWO,
            "snapshot": True,
            "online_resize": True,
            "wffc": True,
            "default": True,
        }
    },
]

storage_class_a = StorageClassNames.TOPOLVM
storage_class_b = StorageClassNames.TOPOLVM

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str, int]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
