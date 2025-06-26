from typing import Any

from pytest_testconfig import config as py_config

from utilities.virt import get_windows_os_dict

# Common templates

RHEL_LATEST: dict[str, Any] = py_config.get("latest_rhel_os_dict", {})
RHEL_LATEST_LABELS: dict[str, Any] = RHEL_LATEST.get("template_labels", {})
RHEL_LATEST_OS: str | None = RHEL_LATEST_LABELS.get("os")

WINDOWS_10: dict[str, Any] = get_windows_os_dict(windows_version="win-10")
WINDOWS_10_TEMPLATE_LABELS: dict[str, Any] = WINDOWS_10.get("template_labels", {})
WINDOWS_11: dict[str, Any] = get_windows_os_dict(windows_version="win-11")
WINDOWS_11_TEMPLATE_LABELS: dict[str, Any] = WINDOWS_11.get("template_labels", {})
WINDOWS_2019: dict[str, Any] = get_windows_os_dict(windows_version="win-2019")
WINDOWS_2019_TEMPLATE_LABELS: dict[str, Any] = WINDOWS_2019.get("template_labels", {})
WINDOWS_2019_OS: str | None = WINDOWS_2019_TEMPLATE_LABELS.get("os")
WINDOWS_LATEST: dict[str, Any] = py_config.get("latest_windows_os_dict", {})
WINDOWS_LATEST_LABELS: dict[str, Any] = WINDOWS_LATEST.get("template_labels", {})
WINDOWS_LATEST_OS: str | None = WINDOWS_LATEST_LABELS.get("os")
WINDOWS_LATEST_VERSION: str | None = WINDOWS_LATEST.get("os_version")

FEDORA_LATEST: dict[str, Any] = py_config.get("latest_fedora_os_dict", {})
FEDORA_LATEST_LABELS: dict[str, Any] = FEDORA_LATEST.get("template_labels", {})
FEDORA_LATEST_OS: str | None = FEDORA_LATEST_LABELS.get("os")
