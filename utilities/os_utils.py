import os
from typing import Any

from ocp_resources.template import Template

from utilities.constants import (
    DATA_SOURCE_NAME,
    DV_SIZE_STR,
    FLAVOR_STR,
    IMAGE_NAME_STR,
    IMAGE_PATH_STR,
    INSTANCE_TYPE_STR,
    LATEST_RELEASE_STR,
    OS_STR,
    OS_VERSION_STR,
    PREFERENCE_STR,
    TEMPLATE_LABELS_STR,
    WIN_2K22,
    WIN_2K25,
    WIN_10,
    WIN_11,
    WORKLOAD_STR,
    Images,
)

RHEL_OS_MAPPING: dict[str, dict[str, Any]] = {
    WORKLOAD_STR: Template.Workload.SERVER,
    FLAVOR_STR: Template.Flavor.TINY,
    "rhel-7-9": {
        IMAGE_NAME_STR: "RHEL7_9_IMG",
        OS_VERSION_STR: "7.9",
        OS_STR: "rhel7.9",
    },
    "rhel-8-10": {
        IMAGE_NAME_STR: "RHEL8_10_IMG",
        OS_VERSION_STR: "8.10",
        OS_STR: "rhel8.10",
    },
    "rhel-9-5": {
        IMAGE_NAME_STR: "RHEL9_5_IMG",
        OS_VERSION_STR: "9.5",
        OS_STR: "rhel9.5",
    },
    "rhel-9-6": {
        IMAGE_NAME_STR: "RHEL9_6_IMG",
        OS_VERSION_STR: "9.6",
        OS_STR: "rhel9.6",
    },
}

WINDOWS_OS_MAPPING: dict[str, dict[str, str | Any]] = {
    WORKLOAD_STR: Template.Workload.SERVER,
    FLAVOR_STR: Template.Flavor.MEDIUM,
    "win-10": {
        IMAGE_NAME_STR: "WIN10_IMG",
        OS_VERSION_STR: "10",
        OS_STR: WIN_10,
        WORKLOAD_STR: Template.Workload.DESKTOP,
        FLAVOR_STR: Template.Flavor.MEDIUM,
        "uefi": True,
    },
    "win-2016": {
        IMAGE_NAME_STR: "WIN2k16_IMG",
        OS_VERSION_STR: "2016",
        OS_STR: "win2k16",
        "uefi": True,
    },
    "win-2019": {
        IMAGE_NAME_STR: "WIN2k19_IMG",
        OS_VERSION_STR: "2019",
        OS_STR: "win2k19",
        "uefi": True,
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
        "uefi": True,
    },
}

FEDORA_OS_MAPPING: dict[str, dict[str, str | Any]] = {
    WORKLOAD_STR: Template.Workload.SERVER,
    FLAVOR_STR: Template.Flavor.SMALL,
    "fedora-41": {
        IMAGE_NAME_STR: "FEDORA41_IMG",
        OS_VERSION_STR: "41",
        OS_STR: "fedora41",
    },
}

CENTOS_OS_MAPPING: dict[str, dict[str, str | Any]] = {
    WORKLOAD_STR: Template.Workload.SERVER,
    FLAVOR_STR: Template.Flavor.TINY,
    "centos-stream-9": {
        IMAGE_NAME_STR: "CENTOS_STREAM_9_IMG",
        OS_VERSION_STR: "9",
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
                    "rhel-7-9": {
                        OS_VERSION_STR: "7.9",
                        IMAGE_NAME_STR: "rhel-79.qcow2",
                        IMAGE_PATH_STR: "cnv-tests/rhel-images/rhel-79.qcow2",
                        DV_SIZE_STR:  "20Gi",
                        TEMPLATE_LABELS_STR: {
                            OS_STR: "rhel7.9",
                            WORKLOAD_STR: "server",
                            FLAVOR_STR: "tiny",
                            },
                        }
                    }
                ]

    Raises:
        ValueError: If the OS name is not supported or if the supported operating systems list is empty.
    """
    os_mappings = {
        "rhel": RHEL_OS_MAPPING,
        "windows": WINDOWS_OS_MAPPING,
        "fedora": FEDORA_OS_MAPPING,
        "centos": CENTOS_OS_MAPPING,
    }
    base_dict = os_mappings.get(os_name)
    if not base_dict:
        raise ValueError(f"Unsupported OS: {os_name}. Supported: rhel, windows, fedora, centos")

    os_base_class = getattr(Images, os_name.title(), None)
    if not os_base_class:
        raise ValueError(
            f"Unsupported OS: {os_name}. "
            "Make sure it is supported under `utilities.constants.ArchImages` class for cluster architecture."
        )

    latest_os_release = getattr(os_base_class, "LATEST_RELEASE_STR", None)
    if not latest_os_release:
        raise ValueError(f"{os_name} is missing `LATEST_RELEASE_STR` attribute")

    dv_size = getattr(os_base_class, "DEFAULT_DV_SIZE", None)
    if not dv_size:
        raise ValueError(f"{os_name} is missing `DEFAULT_DV_SIZE` attribute")

    os_formatted_list: list[dict[str, dict[str, str | bool]]] = []
    unsupported_versions: list[str] = []

    for version in supported_operating_systems:
        if base_version_dict := base_dict.get(version):
            image_name_str = base_dict[version][IMAGE_NAME_STR]
            image_name = getattr(os_base_class, image_name_str, None)
            if not image_name:
                raise ValueError(f"{os_name} is missing {image_name_str} attribute")

            if base_version_dict.get("uefi"):
                image_path_str = getattr(os_base_class, "UEFI_WIN_DIR", None)
                if not image_path_str:
                    raise ValueError(f"{os_name} is missing `UEFI_WIN_DIR` attribute")

            else:
                image_path_str = getattr(os_base_class, "DIR", None)
                if not image_path_str:
                    raise ValueError(f"{os_name} is missing `DIR` attribute")

            os_base_dict = {
                OS_VERSION_STR: base_version_dict[OS_VERSION_STR],
                IMAGE_NAME_STR: image_name,
                IMAGE_PATH_STR: os.path.join(image_path_str, image_name),
                DV_SIZE_STR: dv_size,
                TEMPLATE_LABELS_STR: {
                    OS_STR: base_version_dict[OS_STR],
                    WORKLOAD_STR: base_version_dict.get(WORKLOAD_STR, base_dict[WORKLOAD_STR]),
                    FLAVOR_STR: base_version_dict.get(FLAVOR_STR, base_dict[FLAVOR_STR]),
                },
            }

            if image_name == latest_os_release:
                os_base_dict[LATEST_RELEASE_STR] = True

            os_formatted_list.append({version: os_base_dict})

        else:
            unsupported_versions.append(version)

    if unsupported_versions:
        raise ValueError(f"Unsupported OS versions: {unsupported_versions} for {os_name}")

    return os_formatted_list


def generate_instance_type_rhel_os_matrix(preferences: list[str]) -> list[dict[str, dict[str, Any]]]:
    """
    Generate a list of dictionaries representing the instance type matrix for RHEL OS.

    Each dictionary represents a specific instance type and its configuration.

    Args:
        preferences (list[str]): A list of preferences for the instance types. Preference format is "rhel-<version>".

    Returns:
        list[dict[str, dict[str, Any]]]: A list of dictionaries representing the instance type matrix.
    """
    base_instance_type_spec: dict[str, str] = {
        DV_SIZE_STR: Images.Rhel.DEFAULT_DV_SIZE,
        INSTANCE_TYPE_STR: "u1.medium",
    }
    latest_rhel = "rhel-10"
    if latest_rhel not in preferences:
        latest_rhel = f"rhel-{max([preference.split('-')[1] for preference in preferences])}"

    instance_types: list[dict[str, dict[str, Any]]] = []

    for preference in preferences:
        preference_config: dict[str, Any] = {
            **base_instance_type_spec,
            PREFERENCE_STR: preference.replace("-", "."),
            DATA_SOURCE_NAME: preference.replace("-", ""),
        }
        if preference == latest_rhel:
            preference_config[LATEST_RELEASE_STR] = True

        instance_types.append({preference: preference_config})

    return instance_types
