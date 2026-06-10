import pytest
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import config as py_config

from tests.storage.constants import (
    QUAY_FEDORA_CONTAINER_IMAGE,
    WIN2022_GOLDEN_IMAGE_OS_VERSION,
    WIN2022_GOLDEN_IMAGE_TEMPLATE_LABELS,
)
from utilities.constants import REGISTRY_STR, Images, NamespacesNames
from utilities.storage import create_dv, data_volume


@pytest.fixture()
def windows_source_dv_scope_function(
    request,
    namespace,
    storage_class_matrix__function__,
):
    win_ds_name = py_config.get("win_golden_image_name")
    if win_ds_name:
        storage_class = next(iter(storage_class_matrix__function__))
        with create_dv(
            dv_name="dv-source-gi",
            namespace=namespace.name,
            size=Images.Windows.DEFAULT_DV_SIZE,
            storage_class=storage_class,
            client=namespace.client,
            source_ref={
                "kind": "DataSource",
                "name": win_ds_name,
                "namespace": NamespacesNames.OPENSHIFT_VIRTUALIZATION_OS_IMAGES,
            },
        ) as dv:
            dv.wait_for_dv_success()
            yield dv
    else:
        yield from data_volume(
            request=request,
            namespace=namespace,
            storage_class_matrix=storage_class_matrix__function__,
            client=namespace.client,
        )


@pytest.fixture()
def vm_params(request):
    if py_config.get("win_golden_image_name"):
        return {
            "vm_name": f"vm-win-{WIN2022_GOLDEN_IMAGE_OS_VERSION}-clone",
            "template_labels": WIN2022_GOLDEN_IMAGE_TEMPLATE_LABELS,
            "os_version": WIN2022_GOLDEN_IMAGE_OS_VERSION,
            "ssh": True,
        }
    return request.param


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
