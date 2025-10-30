import os
import re
from pathlib import Path

import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass
from pytest_testconfig import config as py_config


@pytest.fixture()
def updated_default_storage_class_scope_function(
    admin_client,
    storage_class_from_config_different_from_default,
    removed_default_storage_classes,
):
    sc = StorageClass(client=admin_client, name=storage_class_from_config_different_from_default)
    with ResourceEditor(
        patches={
            sc: {
                "metadata": {
                    "annotations": {StorageClass.Annotations.IS_DEFAULT_VIRT_CLASS: "true"},
                    "name": storage_class_from_config_different_from_default,
                }
            }
        }
    ):
        yield sc


@pytest.fixture(scope="module")
def latest_fedora_release_version(downloaded_latest_libosinfo_db):
    """
    Extract the version from file name, if no files found raise KeyError
    file example: /tmp/pytest-6axFnW3vzouCkjWokhvbDi/osinfodb0/osinfo-db-20221121/os/fedoraproject.org/fedora-42.xml
    """
    osinfo_file_folder_path = os.path.join(downloaded_latest_libosinfo_db, "os/fedoraproject.org/")
    list_of_fedora_os_files = list(sorted(Path(osinfo_file_folder_path).glob("*fedora-[0-9][0-9]*.xml")))
    if not list_of_fedora_os_files:
        raise FileNotFoundError("No fedora files were found in osinfo db")
    latest_fedora_os_file = list_of_fedora_os_files[-1]
    return re.findall(r"\d+", latest_fedora_os_file.name)[0]


@pytest.fixture(scope="module")
def storage_class_from_config_different_from_default(rwx_fs_available_storage_classes_names):
    different_storage_class = next(
        (
            storage_class_name
            for storage_class_name in rwx_fs_available_storage_classes_names
            if storage_class_name != py_config["default_storage_class"]
        ),
        None,
    )
    if different_storage_class is None:
        pytest.xfail("No additional storage class found to run the test")
    return different_storage_class
