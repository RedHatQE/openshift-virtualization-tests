import pytest
from ocp_resources.datavolume import DataVolume

from tests.storage.cdi_clone.constants import WINDOWS_CLONE_TIMEOUT
from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE
from tests.utils import create_windows2022_dv_from_registry
from utilities.constants import REGISTRY_STR, WIN_2K22, Images
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
def source_dv_windows_registry_scope_class(
    unprivileged_client,
    namespace,
    storage_class_name_scope_class,
):
    """Fixture that creates a Windows 2022 DataVolume from registry."""
    with create_windows2022_dv_from_registry(
        dv_name=f"dv-source-{WIN_2K22}-registry",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_class,
    ) as dv:
        dv.wait_for_dv_success(timeout=WINDOWS_CLONE_TIMEOUT)
        yield dv


@pytest.fixture(scope="class")
def cloned_windows_dv_scope_class(
    unprivileged_client,
    source_dv_windows_registry_scope_class,
):
    """Fixture that creates a cloned DataVolume from registry source."""
    source_dv_spec = source_dv_windows_registry_scope_class.instance.spec
    with create_dv(
        client=unprivileged_client,
        source="pvc",
        dv_name=f"dv-target-{WIN_2K22}-clone",
        namespace=source_dv_windows_registry_scope_class.namespace,
        size=Images.Windows.CONTAINER_DISK_DV_SIZE,
        source_pvc=source_dv_windows_registry_scope_class.name,
        storage_class=source_dv_spec.storage.storageClassName,
    ) as cdv:
        cdv.wait_for_dv_success(timeout=WINDOWS_CLONE_TIMEOUT)
        yield cdv
