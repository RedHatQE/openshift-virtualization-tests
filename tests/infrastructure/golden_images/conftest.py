import logging

import pytest
import requests
from ocp_resources.data_source import DataSource
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass

from utilities.constants import OS_FLAVOR_FEDORA, TIMEOUT_30SEC

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def updated_default_storage_class_scope_function(
    admin_client,
    storage_class_matrix__function__,
    removed_default_storage_classes,
):
    sc_name = [*storage_class_matrix__function__][0]
    sc = StorageClass(client=admin_client, name=sc_name)
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


@pytest.fixture(scope="module")
def fedora_data_source(unprivileged_client, golden_images_namespace):
    return DataSource(
        client=unprivileged_client, name=OS_FLAVOR_FEDORA, namespace=golden_images_namespace.name, ensure_exists=True
    )
