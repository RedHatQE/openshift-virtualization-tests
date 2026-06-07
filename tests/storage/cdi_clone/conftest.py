import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import py_config

from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE
from utilities.constants import REGISTRY_STR, Images
from utilities.storage import create_dv, data_volume
from utilities.virt import vm_instance_from_template, wait_for_windows_vm


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


@pytest.fixture(scope="module")
def windows2022_golden_image_data_source(golden_images_namespace):
    return DataSource(
        namespace=golden_images_namespace.name,
        name="windows2022-golden-image",
        client=golden_images_namespace.client,
        ensure_exists=True,
    )


@pytest.fixture()
def windows_vm_from_golden_image(
    request,
    unprivileged_client,
    namespace,
    windows2022_golden_image_data_source,
):
    py_config.setdefault("os_login_param", {})["win"] = {
        "username": "Administrator",
        "password": "Heslo123",
    }
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=windows2022_golden_image_data_source,
    ) as vm:
        wait_for_windows_vm(vm=vm, version=request.param["os_version"])
        yield vm
