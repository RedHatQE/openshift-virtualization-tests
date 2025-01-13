from typing import Any

import pytest_testconfig

from utilities.infra import generate_latest_os_dict

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

fedora_os_matrix = [
    generate_latest_os_dict(os_list=config["fedora_os_matrix"])  # noqa: F821
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
