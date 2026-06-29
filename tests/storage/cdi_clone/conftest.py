import pytest
from ocp_resources.datavolume import DataVolume

from tests.storage.cdi_clone.constants import WINDOWS_CLONE_TIMEOUT
from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE
from utilities.constants import WIN_2K22, Images
from utilities.constants.storage import REGISTRY_STR
from utilities.storage import create_dv, data_volume


@pytest.fixture()
def data_volume_snapshot_capable_storage_scope_function(
    request,
    unprivileged_client,
    namespace,
    storage_class_matrix_snapshot_matrix__function__,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix_snapshot_matrix__function__,
        client=namespace.client,
    )


@pytest.fixture(scope="module")
def fedora_dv_with_filesystem_volume_mode(
    unprivileged_client,
    namespace,
    storage_class_with_filesystem_volume_mode,
):
    with create_dv(
        dv_name="dv-fedora-fs",
        namespace=namespace.name,
        source=REGISTRY_STR,
        url=QUAY_FEDORA_CONTAINER_IMAGE,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=storage_class_with_filesystem_volume_mode,
        volume_mode=DataVolume.VolumeMode.FILE,
        client=unprivileged_client,
    ) as dv:
        dv.wait_for_dv_success()
        yield dv


@pytest.fixture(scope="module")
def fedora_dv_with_block_volume_mode(
    unprivileged_client,
    namespace,
    storage_class_with_block_volume_mode,
):
    with create_dv(
        dv_name="dv-fedora-block",
        namespace=namespace.name,
        source=REGISTRY_STR,
        url=QUAY_FEDORA_CONTAINER_IMAGE,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=storage_class_with_block_volume_mode,
        volume_mode=DataVolume.VolumeMode.BLOCK,
        client=unprivileged_client,
    ) as dv:
        dv.wait_for_dv_success()
        yield dv


@pytest.fixture(scope="class")
def cloned_windows_dv_multi_storage_scope_class(
    unprivileged_client,
    namespace,
    storage_class_name_scope_class,
    windows_validation_os_images_data_source_scope_session,
):
    """Fixture that creates a cloned DataVolume from a Windows DataSource."""
    with create_dv(
        client=unprivileged_client,
        dv_name=f"dv-target-{WIN_2K22}-clone",
        namespace=namespace.name,
        size=Images.Windows.CONTAINER_DISK_DV_SIZE,
        storage_class=storage_class_name_scope_class,
        source_ref={
            "kind": windows_validation_os_images_data_source_scope_session.kind,
            "name": windows_validation_os_images_data_source_scope_session.name,
            "namespace": windows_validation_os_images_data_source_scope_session.namespace,
        },
    ) as cdv:
        cdv.wait_for_dv_success(timeout=WINDOWS_CLONE_TIMEOUT)
        yield cdv
