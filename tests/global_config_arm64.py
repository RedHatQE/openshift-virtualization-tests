from typing import Any

import pytest_testconfig

from utilities.constants import (
    ARM_64,
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    PREFERENCE_STR,
    Images,
)

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

Images.Cirros.RAW_IMG_XZ = "cirros-0.4.0-aarch64-disk.raw.xz"
EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{ARM_64}"


for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
