import logging

import pytest
import requests
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass

from utilities.constants import HOSTPATH_CSI_BASIC, TIMEOUT_30SEC

LOGGER = logging.getLogger(__name__)


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
def latest_fedora_release_version():
    response = requests.get(url="https://fedoraproject.org/releases.json", verify=False, timeout=TIMEOUT_30SEC)
    response.raise_for_status()
    response_json = response.json()
    versions = {int(item["version"]) for item in response_json if item.get("version", "").isdigit()}
    if not versions:
        raise ValueError(f"No Fedora versions found in release json: {response_json}")
    latest_fedora_version = str(max(versions))
    LOGGER.info(f"Latest Fedora release: {latest_fedora_version}")
    return latest_fedora_version


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
