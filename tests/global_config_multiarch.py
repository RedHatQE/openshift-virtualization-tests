from typing import Any

from ocp_resources.datavolume import DataVolume

from utilities.constants.architecture import (
    AMD_64,
    ARM_64,
)
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.instance_types import (
    CENTOS_STREAM9_PREFERENCE,
    CENTOS_STREAM10_PREFERENCE,
    RHEL8_PREFERENCE,
    RHEL9_PREFERENCE,
    RHEL10_PREFERENCE,
    U1_MEDIUM_STR,
)
from utilities.constants.storage import StorageClassNames

global config


storage_class_matrix = [
    {
        StorageClassNames.IO2_CSI: {
            "volume_mode": DataVolume.VolumeMode.BLOCK,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": True,
            "default": True,
        }
    },
    {
        StorageClassNames.CEPH_RBD_VIRTUALIZATION: {
            "volume_mode": DataVolume.VolumeMode.BLOCK,
            "access_mode": DataVolume.AccessMode.RWX,
            "snapshot": True,
            "online_resize": True,
            "wffc": False,
        }
    },
]

storage_class_a = StorageClassNames.IO2_CSI
storage_class_b = StorageClassNames.IO2_CSI

os_matrix = {
    AMD_64: {
        "rhel_os_list": ["rhel-8-10", "rhel-9-6"],
        "fedora_os_list": ["fedora-43"],
        "centos_os_list": ["centos-stream-9"],
        "windows_os_list": ["win-10", "win-2019", "win-11", "win-2022", "win-2025"],
        "instance_type_rhel_os_list": [RHEL8_PREFERENCE, RHEL9_PREFERENCE, RHEL10_PREFERENCE],
        "instance_type_fedora_os_list": [OS_FLAVOR_FEDORA],
        "instance_type_centos_os_list": [CENTOS_STREAM9_PREFERENCE, CENTOS_STREAM10_PREFERENCE],
        "data_import_cron_matrix": [
            {"centos-stream9-amd64": {"instance_type": U1_MEDIUM_STR, "preference": CENTOS_STREAM9_PREFERENCE}},
            {"centos-stream10-amd64": {"instance_type": U1_MEDIUM_STR, "preference": CENTOS_STREAM10_PREFERENCE}},
            {"fedora-amd64": {"instance_type": U1_MEDIUM_STR, "preference": OS_FLAVOR_FEDORA}},
            {"rhel8-amd64": {"instance_type": U1_MEDIUM_STR, "preference": RHEL8_PREFERENCE}},
            {"rhel9-amd64": {"instance_type": U1_MEDIUM_STR, "preference": RHEL9_PREFERENCE}},
            {"rhel10-amd64": {"instance_type": U1_MEDIUM_STR, "preference": RHEL10_PREFERENCE}},
        ],
        "auto_update_data_source_matrix": [
            {"centos-stream9-amd64": {"template_os": "centos-stream9"}},
            {"fedora-amd64": {"template_os": "fedora"}},
            {"rhel8-amd64": {"template_os": "rhel8.4"}},
            {"rhel9-amd64": {"template_os": "rhel9.0"}},
        ],
    },
    ARM_64: {
        "rhel_os_list": ["rhel-9-6"],
        "fedora_os_list": ["fedora-42"],
        "centos_os_list": ["centos-stream-9"],
        "instance_type_rhel_os_list": [RHEL10_PREFERENCE],
        "instance_type_fedora_os_list": [OS_FLAVOR_FEDORA],
        "instance_type_centos_os_list": [CENTOS_STREAM10_PREFERENCE],
        # centos and rhel8 have no arm64-specific preferences, while fedora, rhel9 and rhel10 do.
        "data_import_cron_matrix": [
            {"centos-stream9-arm64": {"instance_type": U1_MEDIUM_STR, "preference": CENTOS_STREAM9_PREFERENCE}},
            {"centos-stream10-arm64": {"instance_type": U1_MEDIUM_STR, "preference": CENTOS_STREAM10_PREFERENCE}},
            {"fedora-arm64": {"instance_type": U1_MEDIUM_STR, "preference": f"{OS_FLAVOR_FEDORA}.{ARM_64}"}},
            {"rhel8-arm64": {"instance_type": U1_MEDIUM_STR, "preference": RHEL8_PREFERENCE}},
            {"rhel9-arm64": {"instance_type": U1_MEDIUM_STR, "preference": f"{RHEL9_PREFERENCE}.{ARM_64}"}},
            {"rhel10-arm64": {"instance_type": U1_MEDIUM_STR, "preference": f"{RHEL10_PREFERENCE}.{ARM_64}"}},
        ],
        "auto_update_data_source_matrix": [
            {"centos-stream9-arm64": {"template_os": "centos-stream9"}},
            {"fedora-arm64": {"template_os": "fedora"}},
            {"rhel9-arm64": {"template_os": "rhel9.0"}},
        ],
    },
}


for _dir in dir():
    if not config:
        config: dict[str, Any] = {}
    val = locals()[_dir]
    if type(val) not in [bool, list, dict, str]:
        continue

    if _dir in ["encoding", "py_file"]:
        continue

    config[_dir] = locals()[_dir]
