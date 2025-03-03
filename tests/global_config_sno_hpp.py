from typing import Any

import pytest_testconfig

from utilities.constants import ALL_CNV_DAEMONSETS, ALL_CNV_DEPLOYMENTS, ALL_CNV_PODS, HPP_VOLUME_MODE_ACCESS_MODE
from utilities.storage import HppCsiStorageClass

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")


cnv_deployment_matrix = ALL_CNV_DEPLOYMENTS
cnv_pod_matrix = ALL_CNV_PODS
cnv_daemonset_matrix = ALL_CNV_DAEMONSETS


storage_class_matrix = [
    {HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC: HPP_VOLUME_MODE_ACCESS_MODE},
    {HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_BLOCK: HPP_VOLUME_MODE_ACCESS_MODE},
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
