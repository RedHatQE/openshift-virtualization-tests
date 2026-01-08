from typing import Any

from utilities.constants import (
    CENTOS_STREAM9_PREFERENCE,
    CENTOS_STREAM10_PREFERENCE,
    OS_FLAVOR_FEDORA,
    RHEL8_PREFERENCE,
    RHEL9_PREFERENCE,
    RHEL10_PREFERENCE,
)

global config

rhel_os_list = ["rhel-7-9", "rhel-8-10", "rhel-9-6"]
windows_os_list = ["win-10", "win-2016", "win-2019", "win-11", "win-2022", "win-2025"]
fedora_os_list = ["fedora-43"]
centos_os_list = ["centos-stream-9"]

instance_type_rhel_os_list = [RHEL8_PREFERENCE, RHEL9_PREFERENCE, RHEL10_PREFERENCE]
instance_type_centos_os_list = [CENTOS_STREAM9_PREFERENCE, CENTOS_STREAM10_PREFERENCE]
instance_type_fedora_os_list = [OS_FLAVOR_FEDORA]


for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
