from typing import Any

import utilities.constants
from utilities.constants import (
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    PREFERENCE_STR,
    S390X,
)
from utilities.infra import get_latest_os_dict_list
from utilities.os_utils import generate_linux_instance_type_os_matrix, generate_os_matrix_dict

global config


EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{S390X}"

rhel_os_matrix = generate_os_matrix_dict(
    os_name="rhel",
    supported_operating_systems=[
        "rhel-8-10",
        "rhel-9-6",
    ],
)
fedora_os_matrix = generate_os_matrix_dict(os_name="fedora", supported_operating_systems=["fedora-42"])
centos_os_matrix = generate_os_matrix_dict(os_name="centos", supported_operating_systems=["centos-stream-9"])

instance_type_rhel_os_matrix = generate_linux_instance_type_os_matrix(
    os_name="rhel", preferences=[utilities.constants.RHEL9_PREFERENCE]
)

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
