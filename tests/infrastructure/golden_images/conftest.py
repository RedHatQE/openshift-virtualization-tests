import logging

import pytest
import requests
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass
from pytest_testconfig import config as py_config

from utilities.constants import TIMEOUT_30SEC

LOGGER = logging.getLogger(__name__)


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
def storage_class_from_config_different_from_default(available_storage_classes_names):
    different_storage_class = next(
        (
            storage_class_name
            for storage_class_name in available_storage_classes_names
            if storage_class_name != py_config["default_storage_class"]
        ),
        None,
    )
    if different_storage_class is None:
        pytest.xfail("No additional storage class found to run the test")
    return different_storage_class
