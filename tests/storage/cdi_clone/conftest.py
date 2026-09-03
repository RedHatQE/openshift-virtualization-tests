import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine_clone import VirtualMachineClone

from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE
from tests.storage.stop_status_utils import dv_stop_status_restart_threshold
from tests.storage.utils import VMWithSeveralBlankDisks
from utilities.constants import Images
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.storage import REGISTRY_STR
from utilities.constants.timeouts import TIMEOUT_10MIN, TIMEOUT_40MIN
from utilities.constants.virt import WIN_2K22
from utilities.storage import (
    create_dv,
    data_volume,
    data_volume_template_with_source_ref_dict,
    get_dv_size_from_datasource,
)
from utilities.virt import running_vm, target_vm_from_cloning_job


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


@pytest.fixture()
def source_vm_with_4_disks(
    skip_if_no_storage_class_for_snapshot,
    unprivileged_client,
    namespace,
    fedora_data_source_scope_module,
    snapshot_storage_class_name_scope_module,
):
    with VMWithSeveralBlankDisks(
        name="fedora-4-disks-clone-source",
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_FEDORA,
        blank_disk_storage_class_name=snapshot_storage_class_name_scope_module,
        num_blank_disks=3,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
            storage_class=snapshot_storage_class_name_scope_module,
        ),
        vm_instance_type_infer=True,
        vm_preference_infer=True,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def target_vm_from_4_disk_clone(
    unprivileged_client,
    namespace,
    source_vm_with_4_disks,
):
    with VirtualMachineClone(
        name="clone-job-4-disks",
        client=unprivileged_client,
        namespace=namespace.name,
        source_name=source_vm_with_4_disks.name,
        target_name="fedora-4-disks-target",
    ) as vmc:
        vmc.wait_for_status(status=VirtualMachineClone.Status.SUCCEEDED, timeout=TIMEOUT_10MIN)
        with target_vm_from_cloning_job(client=unprivileged_client, cloning_job=vmc) as target_vm:
            yield target_vm


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
