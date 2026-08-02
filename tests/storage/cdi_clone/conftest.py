import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_profile import StorageProfile

from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE
from tests.storage.stop_status_utils import dv_stop_status_restart_threshold
from utilities.constants import Images
from utilities.constants.storage import HOST_ASSISTED_CLONE_STRATEGY, REGISTRY_STR
from utilities.constants.timeouts import TIMEOUT_40MIN
from utilities.constants.virt import WIN_2K22
from utilities.storage import (
    create_dv,
    data_source_ref,
    data_volume,
    get_dv_size_from_datasource,
)


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
        dv.wait_for_dv_success(stop_status_func=dv_stop_status_restart_threshold, dv=dv)
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
        dv.wait_for_dv_success(stop_status_func=dv_stop_status_restart_threshold, dv=dv)
        yield dv


@pytest.fixture(scope="module")
def storage_class_with_forced_host_assisted_clone(storage_class_name_scope_module, admin_client):
    storage_profile = StorageProfile(name=storage_class_name_scope_module, client=admin_client)
    with ResourceEditor(patches={storage_profile: {"spec": {"cloneStrategy": HOST_ASSISTED_CLONE_STRATEGY}}}):
        yield storage_class_name_scope_module


@pytest.fixture(scope="module")
def fedora_source_dv_for_clone(
    unprivileged_client,
    namespace,
    fedora_data_source_scope_module,
    storage_class_name_scope_module,
):
    with create_dv(
        dv_name="dv-fedora-clone-source",
        namespace=namespace.name,
        size=get_dv_size_from_datasource(data_source=fedora_data_source_scope_module),
        storage_class=storage_class_name_scope_module,
        client=unprivileged_client,
        source_ref=data_source_ref(fedora_data_source_scope_module),
    ) as dv:
        dv.wait_for_dv_success(stop_status_func=dv_stop_status_restart_threshold, dv=dv)
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
