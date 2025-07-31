from typing import Any

import pytest_testconfig
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment

from utilities.constants import (
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    StorageClassNames,
)

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

hco_namespace = "openshift-cnv"
openshift_apiserver_namespace = "openshift-apiserver"

storage_class_matrix = [
    {
        StorageClassNames.GPFS: {
            "volume_mode": DataVolume.VolumeMode.FILE,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": False,
            "default": True,
        }
    },
]

storage_class_for_storage_migration_a = StorageClassNames.GPFS
storage_class_for_storage_migration_b = StorageClassNames.GPFS

# Pod matrix for chaos
cnv_pod_deletion_test_matrix = [
    {
        "virt-api": {
            "pod_prefix": "virt-api",
            "resource": Deployment,
            "namespace_name": hco_namespace,
            "ratio": 0.5,
            "interval": TIMEOUT_5SEC,
            "max_duration": TIMEOUT_5MIN,
        }
    },
    {
        "apiserver": {
            "pod_prefix": "apiserver",
            "resource": Deployment,
            "namespace_name": openshift_apiserver_namespace,
            "ratio": 0.5,
            "interval": TIMEOUT_5SEC,
            "max_duration": TIMEOUT_5MIN,
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
