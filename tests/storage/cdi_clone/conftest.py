import pytest
from ocp_resources.datavolume import DataVolume

from tests.storage.cdi_clone.constants import WINDOWS_CLONE_TIMEOUT
from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_test_artifact_server_url,
)
from utilities.constants import REGISTRY_STR, WIN_2K22, Images
from utilities.os_utils import get_windows_container_disk_path
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


@pytest.fixture()
def source_dv_windows_registry_scope_function(
    unprivileged_client,
    namespace,
    storage_class_name_scope_function,
):
    """Fixture that creates a Windows 2022 DataVolume from registry."""
    artifactory_secret = get_artifactory_secret(namespace=namespace.name)
    artifactory_config_map = get_artifactory_config_map(namespace=namespace.name)
    registry_url = (
        f"{get_test_artifact_server_url(schema='registry')}/{get_windows_container_disk_path(os_value=WIN_2K22)}"
    )
    try:
        with create_dv(
            dv_name=f"dv-source-{WIN_2K22}-registry",
            namespace=namespace.name,
            client=unprivileged_client,
            source=REGISTRY_STR,
            url=registry_url,
            size=Images.Windows.CONTAINER_DISK_DV_SIZE,
            storage_class=storage_class_name_scope_function,
            secret=artifactory_secret,
            cert_configmap=artifactory_config_map.name,
        ) as dv:
            dv.wait_for_dv_success(timeout=WINDOWS_CLONE_TIMEOUT)
            yield dv
    finally:
        cleanup_artifactory_secret_and_config_map(
            artifactory_secret=artifactory_secret,
            artifactory_config_map=artifactory_config_map,
        )


@pytest.fixture()
def cloned_windows_dv_template_from_registry_scope_function(
    unprivileged_client,
    source_dv_windows_registry_scope_function,
):
    """Fixture that creates a cloned DataVolume from registry source."""
    source_dv_spec = source_dv_windows_registry_scope_function.instance.spec
    with create_dv(
        client=unprivileged_client,
        source="pvc",
        dv_name=f"dv-target-{WIN_2K22}-clone",
        namespace=source_dv_windows_registry_scope_function.namespace,
        size=source_dv_spec.storage.resources.requests.storage,
        source_pvc=source_dv_windows_registry_scope_function.name,
        storage_class=source_dv_spec.storage.storageClassName,
    ) as cdv:
        cdv.wait_for_dv_success(timeout=WINDOWS_CLONE_TIMEOUT)
        cdv.to_dict()
        yield cdv.res
