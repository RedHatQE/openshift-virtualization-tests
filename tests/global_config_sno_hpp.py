from typing import Any

import pytest_testconfig

from utilities.constants.storage import HPP_CAPABILITIES
from utilities.storage import HppCsiStorageClass

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")


storage_class_matrix = [
    {HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC: HPP_CAPABILITIES},
    {HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_BLOCK: HPP_CAPABILITIES},
]


for _dir in dir():
    if not config:
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str, int]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]
