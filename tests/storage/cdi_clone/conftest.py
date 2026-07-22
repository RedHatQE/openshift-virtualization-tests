import pytest
from ocp_resources.datavolume import DataVolume

from utilities.constants.timeouts import TIMEOUT_40MIN
from utilities.constants.virt import WIN_2K22
from utilities.storage import create_dv, data_volume, get_dv_size_from_datasource


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
    fedora_data_source_scope_module,
    storage_class_with_filesystem_volume_mode,
):
    with create_dv(
        dv_name="dv-fedora-fs",
        namespace=namespace.name,
        size=get_dv_size_from_datasource(data_source=fedora_data_source_scope_module),
        storage_class=storage_class_with_filesystem_volume_mode,
        volume_mode=DataVolume.VolumeMode.FILE,
        client=unprivileged_client,
        source_ref={
            "kind": fedora_data_source_scope_module.kind,
            "name": fedora_data_source_scope_module.name,
            "namespace": fedora_data_source_scope_module.namespace,
        },
    ) as dv:
        dv.wait_for_dv_success()
        yield dv


@pytest.fixture(scope="module")
def fedora_dv_with_block_volume_mode(
    unprivileged_client,
    namespace,
    fedora_data_source_scope_module,
    storage_class_with_block_volume_mode,
):
    with create_dv(
        dv_name="dv-fedora-block",
        namespace=namespace.name,
        size=get_dv_size_from_datasource(data_source=fedora_data_source_scope_module),
        storage_class=storage_class_with_block_volume_mode,
        volume_mode=DataVolume.VolumeMode.BLOCK,
        client=unprivileged_client,
        source_ref={
            "kind": fedora_data_source_scope_module.kind,
            "name": fedora_data_source_scope_module.name,
            "namespace": fedora_data_source_scope_module.namespace,
        },
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
    with create_dv(
        client=unprivileged_client,
        dv_name=f"dv-target-{WIN_2K22}-clone",
        namespace=namespace.name,
        size=get_dv_size_from_datasource(windows_validation_os_images_data_source_scope_session),
        storage_class=storage_class_name_scope_class,
        source_ref={
            "kind": windows_validation_os_images_data_source_scope_session.kind,
            "name": windows_validation_os_images_data_source_scope_session.name,
            "namespace": windows_validation_os_images_data_source_scope_session.namespace,
        },
    ) as cdv:
        cdv.wait_for_dv_success(timeout=TIMEOUT_40MIN)
        yield cdv
