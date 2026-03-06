from typing import Any

from utilities.constants import (
    CENTOS_STREAM9_PREFERENCE,
    CENTOS_STREAM10_PREFERENCE,
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    OS_FLAVOR_FEDORA,
    PREFERENCE_STR,
    RHEL9_PREFERENCE,
    RHEL10_PREFERENCE,
    S390X,
)

global config


EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{S390X}"


rhel_os_list = ["rhel-8-10", "rhel-9-6"]
fedora_os_list = ["fedora-42"]
centos_os_list = ["centos-stream-9"]

instance_type_rhel_os_list = [RHEL9_PREFERENCE, RHEL10_PREFERENCE]
instance_type_fedora_os_list = [OS_FLAVOR_FEDORA]
instance_type_centos_os_list = [CENTOS_STREAM9_PREFERENCE, CENTOS_STREAM10_PREFERENCE]


for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
