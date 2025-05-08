import logging

import pytest
from ocp_resources.datavolume import DataVolume

from tests.storage.storage_migration.utils import (
    CONTENT,
    FILE_BEFORE_STORAGE_MIGRATION,
    create_vm_from_data_source_with_instance_type,
    get_source_virt_launcher_pod,
)
from utilities.storage import write_file

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def target_storage_class(request):
    return request.param["target_storage_class"]


@pytest.fixture()
def source_storage_class(request):
    return request.param["source_storage_class"]


@pytest.fixture()
def source_vm_for_storage_class_migration(
    admin_client, namespace, golden_images_fedora_data_source, source_storage_class
):
    with create_vm_from_data_source_with_instance_type(
        vm_name="vm-for-test",
        namespace=namespace.name,
        client=admin_client,  # TODO replace to unpriv before merge
        data_source=golden_images_fedora_data_source,
        storage_class=source_storage_class,
    ) as vm:
        yield vm


@pytest.fixture()
def written_file_to_vm_before_migration(source_vm_for_storage_class_migration):
    write_file(
        vm=source_vm_for_storage_class_migration,
        filename=FILE_BEFORE_STORAGE_MIGRATION,
        content=CONTENT,
        stop_vm=False,
    )


@pytest.fixture()
def deleted_completed_virt_launcher_source_pod(source_vm_for_storage_class_migration):
    source_pod = get_source_virt_launcher_pod(vm=source_vm_for_storage_class_migration)
    source_pod.wait_for_status(status=source_pod.Status.SUCCEEDED)
    source_pod.delete(wait=True)


@pytest.fixture()
def deleted_old_dv(source_vm_for_storage_class_migration):
    dv_name = (
        source_vm_for_storage_class_migration.instance.status.volumeUpdateState.volumeMigrationState.migratedVolumes[
            0
        ].sourcePVCInfo.claimName
    )
    dv = DataVolume(name=dv_name, namespace=source_vm_for_storage_class_migration.namespace)
    assert dv.exists, f"DataVolume {dv_name} is not found"
    dv.delete(wait=True)
