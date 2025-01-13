import pytest
from ocp_resources.datavolume import DataVolume

from tests.storage.utils import create_cirros_dv
from utilities.storage import data_volume


@pytest.fixture(scope="module")
def cirros_dv_with_filesystem_volume_mode(
    namespace,
    storage_class_with_filesystem_volume_mode,
):
    yield from create_cirros_dv(
        namespace=namespace.name,
        name="cirros-fs",
        storage_class=storage_class_with_filesystem_volume_mode,
        volume_mode=DataVolume.VolumeMode.FILE,
    )


@pytest.fixture(scope="module")
def cirros_dv_with_block_volume_mode(
    namespace,
    storage_class_with_block_volume_mode,
):
    yield from create_cirros_dv(
        namespace=namespace.name,
        name="cirros-block",
        storage_class=storage_class_with_block_volume_mode,
        volume_mode=DataVolume.VolumeMode.BLOCK,
    )


@pytest.fixture()
def data_volume_snapshot_capable_storage_scope_function(
    request,
    namespace,
    storage_class_matrix_snapshot_matrix__function__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix_snapshot_matrix__function__,
        schedulable_nodes=schedulable_nodes,
    )
