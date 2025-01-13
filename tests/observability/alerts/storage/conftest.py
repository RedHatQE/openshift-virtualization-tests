import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_class import StorageClass
from pytest_testconfig import py_config

from utilities.constants import Images


@pytest.fixture()
def created_fake_data_volume_resource(namespace):
    with DataVolume(
        name="fake-dv",
        namespace=namespace.name,
        url="http://broken-link.test",
        source="http",
        size=Images.Rhel.DEFAULT_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        bind_immediate_annotation=True,
        api_name="storage",
    ) as dv:
        yield dv


@pytest.fixture()
def created_fake_storage_class_resource():
    with StorageClass(
        name="fake-sc",
        provisioner="fake-provisioner",
        reclaim_policy=StorageClass.ReclaimPolicy.DELETE,
        volume_binding_mode=StorageClass.VolumeBindingMode.Immediate,
    ) as sc:
        yield sc
