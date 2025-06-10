from typing import Any

import pytest_testconfig
from ocp_resources.datavolume import DataVolume

from utilities.constants import StorageClassNames

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config_x86.py", encoding="utf-8")

insecure_skip_tls_verify = True
no_unprivileged_client = True
storage_class_matrix = [
    {
        StorageClassNames.RH_INTERNAL_NFS: {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": False,
            "default": True,
        }
    },
]

storage_class_for_storage_migration_a = StorageClassNames.RH_INTERNAL_NFS
storage_class_for_storage_migration_b = StorageClassNames.RH_INTERNAL_NFS

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
