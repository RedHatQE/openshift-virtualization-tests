import os
from typing import Any

from ocp_resources.template import Template

from utilities.constants import (
    DV_SIZE_STR,
    FLAVOR_STR,
    IMAGE_NAME_STR,
    IMAGE_PATH_STR,
    LATEST_RELEASE_STR,
    OS_STR,
    OS_VERSION_STR,
    TEMPLATE_LABELS_STR,
    WIN_2K22,
    WIN_2K25,
    WIN_10,
    WIN_11,
    WORKLOAD_STR,
    Images,
)

RHEL_OS_MAPPING = {
    WORKLOAD_STR: Template.Workload.SERVER,
    FLAVOR_STR: Template.Flavor.TINY,
    "rhel-7-8": {
        IMAGE_NAME_STR: "RHEL7_8_IMG",
        OS_VERSION_STR: "7.8",
        OS_STR: "rhel7.8",
    },
    "rhel-7-9": {
        IMAGE_NAME_STR: "RHEL7_9_IMG",
        OS_VERSION_STR: "7.9",
        OS_STR: "rhel7.9",
    },
    "rhel-8-8": {
        IMAGE_NAME_STR: "RHEL8_8_IMG",
        OS_VERSION_STR: "8.8",
        OS_STR: "rhel8.8",
    },
    "rhel-8-10": {
        IMAGE_NAME_STR: "RHEL8_10_IMG",
        OS_VERSION_STR: "8.10",
        OS_STR: "rhel8.10",
    },
    "rhel-9-4": {
        IMAGE_NAME_STR: "RHEL9_4_IMG",
        OS_VERSION_STR: "9.4",
        OS_STR: "rhel9.4",
    },
    "rhel-9-5": {
        IMAGE_NAME_STR: "RHEL9_5_IMG",
        OS_VERSION_STR: "9.5",
        OS_STR: "rhel9.5",
    },
    "rhel-9-6": {
        IMAGE_NAME_STR: "RHEL9_6_IMG",
        OS_VERSION_STR: "9.6",
        LATEST_RELEASE_STR: True,
        OS_STR: "rhel9.6",
    },
}

WINDOWS_OS_MAPPING = {
    WORKLOAD_STR: Template.Workload.SERVER,
    FLAVOR_STR: Template.Flavor.MEDIUM,
    "win-10": {
        IMAGE_NAME_STR: "WIN10_IMG",
        OS_VERSION_STR: "10",
        OS_STR: WIN_10,
        WORKLOAD_STR: Template.Workload.DESKTOP,
        FLAVOR_STR: Template.Flavor.MEDIUM,
    },
    "win-2016": {
        IMAGE_NAME_STR: "WIN2k16_IMG",
        OS_VERSION_STR: "2016",
        OS_STR: "win2k16",
    },
    "win-2019": {
        IMAGE_NAME_STR: "WIN2k19_IMG",
        OS_VERSION_STR: "2019",
        LATEST_RELEASE_STR: True,
        OS_STR: "win2k19",
    },
    "win-11": {
        IMAGE_NAME_STR: "WIN11_IMG",
        OS_VERSION_STR: "11",
        OS_STR: WIN_11,
        WORKLOAD_STR: Template.Workload.DESKTOP,
        FLAVOR_STR: Template.Flavor.MEDIUM,
    },
    "win-2022": {
        IMAGE_NAME_STR: "WIN2022_IMG",
        OS_VERSION_STR: "2022",
        OS_STR: WIN_2K22,
    },
    "win-2025": {
        IMAGE_NAME_STR: "WIN2k25_IMG",
        OS_VERSION_STR: "2025",
        OS_STR: WIN_2K25,
    },
}

FEDORA_OS_MAPPING = {
    WORKLOAD_STR: Template.Workload.SERVER,
    FLAVOR_STR: Template.Flavor.SMALL,
    "fedora-41": {
        IMAGE_NAME_STR: "FEDORA41_IMG",
        LATEST_RELEASE_STR: True,
        OS_STR: "fedora41",
    },
}

CENTOS_OS_MAPPING = {
    WORKLOAD_STR: Template.Workload.SERVER,
    FLAVOR_STR: Template.Flavor.TINY,
    "centos-stream-9": {
        IMAGE_NAME_STR: "CENTOS_STREAM_9_IMG",
        LATEST_RELEASE_STR: True,
        OS_STR: "centos-stream9",
    },
}


def generate_os_matrix_dict(os_name: str, supported_operating_systems: list[str]) -> list[dict[str, Any]]:
    """
    Generate a dictionary of OS matrix for the given OS name and supported operating systems.

    Args:
        os_name (str): The name of the OS.
        supported_operating_systems (list[str]): A list of supported operating systems.

    Returns:
        list[dict[str, Any]]: A list of dictionaries representing the OS matrix.

            Example:
                [
                    {
                    "rhel-7-8": {
                        OS_VERSION_STR: "7.8",
                        IMAGE_NAME_STR: "rhel-78.qcow2",
                        IMAGE_PATH_STR: "cnv-tests/rhel-images/rhel-78.qcow2",
                        DV_SIZE_STR:  "20Gi",
                        TEMPLATE_LABELS_STR: {
                            OS_STR: "rhel7.8",
                            WORKLOAD_STR: "server",
                            FLAVOR_STR: "tiny",
                            },
                        }
                    }
                ]

    Raises:
        ValueError: If the OS name is not supported or if the supported operating systems list is empty.
    """
    if os_name == "rhel":
        base_dict = RHEL_OS_MAPPING
    elif os_name == "windows":
        base_dict = WINDOWS_OS_MAPPING
    elif os_name == "fedora":
        base_dict = FEDORA_OS_MAPPING
    elif os_name == "centos":
        base_dict = CENTOS_OS_MAPPING
    else:
        raise ValueError(f"Unsupported OS: {os_name}. Supported: rhel, win, fedora")

    class_name = "CentOS" if os_name == "centos" else os_name.title()
    os_base_class = getattr(Images, class_name)

    os_formatted_list = []
    unsupported_versions = []

    for version in supported_operating_systems:
        if base_version_dict := base_dict.get(version):
            image_name = getattr(os_base_class, base_dict[version][IMAGE_NAME_STR])

            os_formatted_list.append({
                version: {
                    OS_VERSION_STR: base_version_dict.get(OS_VERSION_STR),
                    IMAGE_NAME_STR: image_name,
                    IMAGE_PATH_STR: os.path.join(getattr(os_base_class, "DIR"), image_name),
                    DV_SIZE_STR: getattr(os_base_class, "DEFAULT_DV_SIZE"),
                    TEMPLATE_LABELS_STR: {
                        OS_STR: base_version_dict[OS_STR],
                        WORKLOAD_STR: base_version_dict.get(WORKLOAD_STR, base_dict[WORKLOAD_STR]),
                        FLAVOR_STR: base_version_dict.get(FLAVOR_STR, base_dict[FLAVOR_STR]),
                    },
                    LATEST_RELEASE_STR: base_version_dict.get(LATEST_RELEASE_STR, False),
                }
            })

        else:
            unsupported_versions.append(version)

    if unsupported_versions:
        raise ValueError(f"Unsupported OS versions: {unsupported_versions} for {os_name}")

    return os_formatted_list
