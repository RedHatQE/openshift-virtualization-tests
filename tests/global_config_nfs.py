from typing import Any

import pytest_testconfig
from ocp_resources.datavolume import DataVolume

from utilities.constants import StorageClassNames

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config_x86.py", encoding="utf-8")

storage_class_matrix = [
    {
        StorageClassNames.NFS: {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": False,
            "online_resize": False,
            "wffc": False,
            "default": True,
        }
    },
]

storage_class_for_storage_migration_a = StorageClassNames.NFS
storage_class_for_storage_migration_b = StorageClassNames.NFS

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str, int]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
