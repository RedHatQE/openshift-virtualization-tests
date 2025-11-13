from typing import Any

from utilities.constants import (
    CENTOS_STREAM9_PREFERENCE,
    CENTOS_STREAM10_PREFERENCE,
    OS_FLAVOR_FEDORA,
    RHEL8_PREFERENCE,
    RHEL9_PREFERENCE,
    RHEL10_PREFERENCE,
)
from utilities.infra import get_latest_os_dict_list
from utilities.os_utils import (
    generate_linux_instance_type_os_matrix,
    generate_os_matrix_dict,
)

global config

rhel_os_matrix = generate_os_matrix_dict(
    os_name="rhel",
    supported_operating_systems=[
        "rhel-7-9",
        "rhel-8-10",
        "rhel-9-6",
    ],
)

windows_os_matrix = generate_os_matrix_dict(
    os_name="windows",
    supported_operating_systems=[
        "win-10",
        "win-2016",
        "win-2019",
        "win-11",
        "win-2022",
        "win-2025",
    ],
)

fedora_os_matrix = generate_os_matrix_dict(os_name="fedora", supported_operating_systems=["fedora-43"])
centos_os_matrix = generate_os_matrix_dict(os_name="centos", supported_operating_systems=["centos-stream-9"])
instance_type_rhel_os_matrix = generate_linux_instance_type_os_matrix(
    os_name="rhel", preferences=[RHEL8_PREFERENCE, RHEL9_PREFERENCE, RHEL10_PREFERENCE]
)
instance_type_centos_os_matrix = generate_linux_instance_type_os_matrix(
    os_name="centos.stream", preferences=[CENTOS_STREAM9_PREFERENCE, CENTOS_STREAM10_PREFERENCE]
)
instance_type_fedora_os_matrix = generate_linux_instance_type_os_matrix(
    os_name=OS_FLAVOR_FEDORA, preferences=[OS_FLAVOR_FEDORA]
)

(
    latest_rhel_os_dict,
    latest_windows_os_dict,
    latest_fedora_os_dict,
    latest_centos_os_dict,
) = get_latest_os_dict_list(os_list=[rhel_os_matrix, windows_os_matrix, fedora_os_matrix, centos_os_matrix])


for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
