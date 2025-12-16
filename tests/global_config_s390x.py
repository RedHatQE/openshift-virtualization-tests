from typing import Any

import utilities.constants
from utilities.constants import (
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    PREFERENCE_STR,
    S390X,
)

global config


EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR] = f"rhel.9.{S390X}"


rhel_os_list = ["rhel-8-10", "rhel-9-6"]
fedora_os_list = ["fedora-42"]
centos_os_list = ["centos-stream-9"]

instance_type_rhel_os_list = [utilities.constants.RHEL9_PREFERENCE]
instance_type_fedora_os_list = [utilities.constants.OS_FLAVOR_FEDORA]
instance_type_centos_os_list = [utilities.constants.CENTOS_STREAM9_PREFERENCE]


for _dir in dir():
    if not config:  # noqa: F821
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]  # noqa: F821
