from typing import Any

from ocp_resources.datavolume import DataVolume
from pytest_testconfig import load_python

from utilities.constants import StorageClassNames

global config
global_config = load_python(py_file="tests/global_config.py", encoding="utf-8")

storage_class_matrix = [
    {
        StorageClassNames.GCNV: {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": False,
            "default": True,
        }
    }
]

storage_class_a = StorageClassNames.GCNV
storage_class_b = StorageClassNames.GCNV

config: dict[str, Any] = globals().get("config") or {}

for dir_name in dir():
    val = locals()[dir_name]
    if type(val) not in [bool, list, dict, str]:
        continue

    if dir_name in ["encoding", "py_file"]:
        continue

    config[dir_name] = val
