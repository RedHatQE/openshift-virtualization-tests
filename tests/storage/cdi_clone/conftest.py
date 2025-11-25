import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume

from tests.storage.utils import create_cirros_dv
from utilities.constants import OS_FLAVOR_FEDORA
from utilities.storage import data_volume


@pytest.fixture(scope="module")
def cirros_dv_with_filesystem_volume_mode(
    unprivileged_client,
    namespace,
    storage_class_with_filesystem_volume_mode,
):
    yield from create_cirros_dv(
        client=unprivileged_client,
        namespace=namespace.name,
        name="cirros-fs",
        storage_class=storage_class_with_filesystem_volume_mode,
        volume_mode=DataVolume.VolumeMode.FILE,
    )


@pytest.fixture(scope="module")
def cirros_dv_with_block_volume_mode(
    unprivileged_client,
    namespace,
    storage_class_with_block_volume_mode,
):
    yield from create_cirros_dv(
        client=unprivileged_client,
        namespace=namespace.name,
        name="cirros-block",
        storage_class=storage_class_with_block_volume_mode,
        volume_mode=DataVolume.VolumeMode.BLOCK,
    )


@pytest.fixture()
def data_volume_snapshot_capable_storage_scope_function(
    request,
    unprivileged_client,
    namespace,
    storage_class_matrix_snapshot_matrix__function__,
    schedulable_nodes,
):
    yield from data_volume(
        client=unprivileged_client,
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix_snapshot_matrix__function__,
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="module")
def fedora_data_source_scope_module(golden_images_namespace):
    return DataSource(
        namespace=golden_images_namespace.name,
        name=OS_FLAVOR_FEDORA,
        client=golden_images_namespace.client,
        ensure_exists=True,
    )
