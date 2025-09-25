import os
import re
from pathlib import Path

import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass


@pytest.fixture()
def updated_default_storage_class_scope_function(
    admin_client,
    storage_class_matrix__function__,
    removed_default_storage_classes,
):
    sc_name = [*storage_class_matrix__function__][0]
    sc = StorageClass(name=sc_name)
    with ResourceEditor(
        patches={
            sc: {
                "metadata": {
                    "annotations": {StorageClass.Annotations.IS_DEFAULT_VIRT_CLASS: "true"},
                    "name": sc_name,
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
