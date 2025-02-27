import os
import re
from pathlib import Path

import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass

from utilities.constants import HOSTPATH_CSI_BASIC, StorageClassNames


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
    file example: /tmp/pytest-6axFnW3vzouCkjWokhvbDi/osinfodb0/osinfo-db-20221121/os/fedoraproject.org/fedora-41.xml
    """
    osinfo_file_folder_path = os.path.join(downloaded_latest_libosinfo_db, "os/fedoraproject.org/")
    list_of_fedora_os_files = list(sorted(Path(osinfo_file_folder_path).glob("*fedora-[0-9][0-9]*.xml")))
    if not list_of_fedora_os_files:
        raise FileNotFoundError("No fedora files were found in osinfo db")
    latest_fedora_os_file = list_of_fedora_os_files[-1]
    return re.findall(r"\d+", latest_fedora_os_file.name)[0]


@pytest.fixture(scope="session")
def fail_if_no_ceph_rbd_virtualization_sc(cluster_storage_classes_names):
    """
    Fail the test if no NFS storage class is available
    """
    if StorageClassNames.CEPH_RBD_VIRTUALIZATION not in cluster_storage_classes_names:
        pytest.fail(
            f"Test failed: {StorageClassNames.CEPH_RBD_VIRTUALIZATION} storage class is not deployed. "
            f"Available storage classes: {cluster_storage_classes_names}. "
            "Ensure the correct storage class is configured before running tests."
        )


@pytest.fixture(scope="session")
def fail_if_no_hostpath_csi_basic_sc(cluster_storage_classes_names):
    """
    Fail the test if no CSI basic storage class is available
    """
    if HOSTPATH_CSI_BASIC not in cluster_storage_classes_names:
        pytest.fail(
            f"Test failed: {HOSTPATH_CSI_BASIC} basic storage class is not deployed. "
            f"Available storage classes: {cluster_storage_classes_names}. "
            "Ensure the correct CSI storage class is configured before running tests."
        )
