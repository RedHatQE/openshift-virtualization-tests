import re
import shlex

import pytest
import requests
from bs4 import BeautifulSoup
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config

from tests.infrastructure.instance_types.supported_os.utils import golden_image_vm_with_instance_type
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
)
from utilities.constants import (
    CONTAINER_DISK_IMAGE_PATH_STR,
    DATA_SOURCE_NAME,
    DATA_SOURCE_STR,
    RHEL8_PREFERENCE,
    TIMEOUT_30SEC,
    Images,
)
from utilities.storage import get_test_artifact_server_url
from utilities.virt import VirtualMachineForTests


@pytest.fixture(scope="class")
def xfail_if_rhel8(instance_type_rhel_os_matrix__module__):
    if [*instance_type_rhel_os_matrix__module__][0] == RHEL8_PREFERENCE:
        pytest.xfail("EFI is not enabled by default before RHEL9")


def get_all_release_versions_from_docs(major_ver_num):
    """
    Parse the documentation index page to get all release notes versions.

    Args:
        major_ver_num: Major version (e.g., 8, 9, 10)

    Returns:
        list: List of minor version numbers (e.g., [0, 1, 2, 3, 4, 5, 6, 7])
    """
    url = f"https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/{major_ver_num}/"
    response = requests.get(url=url, timeout=TIMEOUT_30SEC)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    versions = []
    pattern = re.compile(
        rf"/en/documentation/red_hat_enterprise_linux/{major_ver_num}/html/{major_ver_num}\.(\d+)_release_notes"
    )

    for link in soup.find_all("a", href=True):
        match = pattern.search(string=link.get("href", ""))
        if match:
            versions.append(int(match.group(1)))
    versions = sorted(set(versions))
    return versions


@pytest.fixture(scope="module")
def latest_rhel_release_versions_dict():
    """
    Parse RHEL documentation pages to find the latest released versions.

    Returns:
        Dictionary mapping major versions to their latest minor versions
        e.g., {8: "8.10", 9: "9.7", 10: "10.1"}
    """
    latest_versions = {}

    for major_ver_num in [8, 9, 10]:
        all_versions = get_all_release_versions_from_docs(major_ver_num=major_ver_num)
        if not all_versions:
            raise ValueError(f"Failed to find RHEL {major_ver_num} versions from documentation")
        latest_versions[major_ver_num] = max(all_versions)

    return {f"rhel.{major}": f"{major}.{minor}" for major, minor in latest_versions.items()}


@pytest.fixture()
def rhel_vm_minor_ver_num(golden_image_rhel_vm_with_instance_type):
    rhel_vm_os_ver = run_ssh_commands(
        host=golden_image_rhel_vm_with_instance_type.ssh_exec,
        commands=(shlex.split("cat /etc/redhat-release")),
    )[0]
    matches = re.findall(r"(?<=\.)(\d+)(?= )", rhel_vm_os_ver)
    if not matches:
        raise ValueError(f"Failed to extract RHEL minor version from: {rhel_vm_os_ver}")
    return matches[0]


@pytest.fixture(scope="module")
def golden_image_rhel_vm_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    instance_type_rhel_os_matrix__module__,
    storage_class_matrix__module__,
):
    os_name = next(iter(instance_type_rhel_os_matrix__module__))
    return golden_image_vm_with_instance_type(
        client=unprivileged_client,
        namespace_name=namespace.name,
        golden_images_namespace_name=golden_images_namespace.name,
        modern_cpu_for_migration=modern_cpu_for_migration,
        storage_class_name=[*storage_class_matrix__module__][0],
        data_source_name=instance_type_rhel_os_matrix__module__[os_name][DATA_SOURCE_NAME],
    )


@pytest.fixture(scope="module")
def golden_image_centos_vm_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    instance_type_centos_os_matrix__module__,
    storage_class_matrix__module__,
):
    os_name = next(iter(instance_type_centos_os_matrix__module__))
    return golden_image_vm_with_instance_type(
        client=unprivileged_client,
        namespace_name=namespace.name,
        golden_images_namespace_name=golden_images_namespace.name,
        modern_cpu_for_migration=modern_cpu_for_migration,
        storage_class_name=[*storage_class_matrix__module__][0],
        data_source_name=instance_type_centos_os_matrix__module__[os_name][DATA_SOURCE_NAME],
    )


@pytest.fixture(scope="module")
def golden_image_fedora_vm_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    modern_cpu_for_migration,
    instance_type_fedora_os_matrix__module__,
    storage_class_matrix__module__,
):
    os_name = next(iter(instance_type_fedora_os_matrix__module__))
    return golden_image_vm_with_instance_type(
        client=unprivileged_client,
        namespace_name=namespace.name,
        golden_images_namespace_name=golden_images_namespace.name,
        modern_cpu_for_migration=modern_cpu_for_migration,
        storage_class_name=[*storage_class_matrix__module__][0],
        data_source_name=instance_type_fedora_os_matrix__module__[os_name][DATA_SOURCE_NAME],
    )


@pytest.fixture(scope="module")
def windows_data_volume_template(
    namespace,
    windows_os_matrix__module__,
):
    os_matrix_key = [*windows_os_matrix__module__][0]
    os_params = windows_os_matrix__module__[os_matrix_key]
    secret = get_artifactory_secret(namespace=namespace.name)
    cert = get_artifactory_config_map(namespace=namespace.name)
    win_dv = DataVolume(
        name=f"{os_matrix_key}-dv",
        namespace=namespace.name,
        api_name="storage",
        source="registry",
        size=Images.Windows.CONTAINER_DISK_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        url=f"{get_test_artifact_server_url(schema='registry')}/{os_params[CONTAINER_DISK_IMAGE_PATH_STR]}",
        secret=secret,
        cert_configmap=cert.name,
    )
    win_dv.to_dict()
    yield win_dv
    cleanup_artifactory_secret_and_config_map(artifactory_secret=secret, artifactory_config_map=cert)


@pytest.fixture(scope="class")
def golden_image_windows_vm(
    unprivileged_client,
    namespace,
    modern_cpu_for_migration,
    windows_data_volume_template,
    windows_os_matrix__module__,
):
    os_name = [*windows_os_matrix__module__][0]
    return VirtualMachineForTests(
        client=unprivileged_client,
        name=f"{os_name}-vm-with-instance-type-2",
        namespace=namespace.name,
        vm_instance_type=VirtualMachineClusterInstancetype(name="u1.large"),
        vm_preference=VirtualMachineClusterPreference(
            name=windows_os_matrix__module__[os_name][DATA_SOURCE_STR].replace("win", "windows.")
        ),
        data_volume_template=windows_data_volume_template.res,
        os_flavor="win-container-disk",
        disk_type=None,
        cpu_model=modern_cpu_for_migration,
    )
