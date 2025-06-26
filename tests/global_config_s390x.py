from typing import Any

import pytest_testconfig

import utilities.constants
from utilities.constants import (
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    PREFERENCE_STR,
    S390X,
)
from utilities.infra import get_latest_os_dict_list
from utilities.os_utils import generate_os_matrix_dict

global config
global_config = pytest_testconfig.load_python(py_file="tests/global_config.py", encoding="utf-8")

utilities.constants.OS_FLAVOR_CIRROS = "fedora"
EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{S390X}"

rhel_os_matrix = generate_os_matrix_dict(os_name="rhel", supported_operating_systems=["rhel-9-5"])
fedora_os_matrix = generate_os_matrix_dict(os_name="fedora", supported_operating_systems=["fedora-41"])
centos_os_matrix = generate_os_matrix_dict(os_name="centos", supported_operating_systems=["centos-stream-9"])

latest_rhel_os_dict, latest_fedora_os_dict, latest_centos_os_dict = get_latest_os_dict_list(
    os_list=[rhel_os_matrix, fedora_os_matrix, centos_os_matrix]
)

for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
