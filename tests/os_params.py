from pytest_testconfig import config as py_config

from utilities.virt import get_rhel_os_dict, get_windows_os_dict

# Common templates

RHEL_LATEST = py_config["latest_rhel_os_dict"]
RHEL_LATEST_LABELS = RHEL_LATEST["template_labels"]
RHEL_LATEST_OS = RHEL_LATEST_LABELS["os"]
RHEL_7_8 = get_rhel_os_dict(rhel_version="rhel-7-8")
RHEL_7_8_TEMPLATE_LABELS = RHEL_7_8["template_labels"]
RHEL_8_10 = get_rhel_os_dict(rhel_version="rhel-8-10")
RHEL_8_10_TEMPLATE_LABELS = RHEL_8_10["template_labels"]

WINDOWS_10 = get_windows_os_dict(windows_version="win-10")
WINDOWS_10_TEMPLATE_LABELS = WINDOWS_10["template_labels"]
WINDOWS_11 = get_windows_os_dict(windows_version="win-11")
WINDOWS_11_TEMPLATE_LABELS = WINDOWS_11["template_labels"]
WINDOWS_2019 = get_windows_os_dict(windows_version="win-2019")
WINDOWS_2019_TEMPLATE_LABELS = WINDOWS_2019["template_labels"]
WINDOWS_2019_OS = WINDOWS_2019_TEMPLATE_LABELS["os"]
WINDOWS_LATEST = py_config["latest_windows_os_dict"]
WINDOWS_LATEST_LABELS = WINDOWS_LATEST["template_labels"]
WINDOWS_LATEST_OS = WINDOWS_LATEST_LABELS["os"]
WINDOWS_LATEST_VERSION = WINDOWS_LATEST["os_version"]

FEDORA_LATEST = py_config["latest_fedora_os_dict"]
FEDORA_LATEST_LABELS = FEDORA_LATEST["template_labels"]
FEDORA_LATEST_OS = FEDORA_LATEST_LABELS["os"]
