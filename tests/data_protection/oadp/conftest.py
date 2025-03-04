import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.namespace import Namespace

from tests.data_protection.oadp.utils import (
    FILE_NAME_FOR_BACKUP,
    TEXT_TO_TEST,
    VeleroBackup,
    VeleroRestore,
    create_rhel_vm,
    is_storage_class_support_volume_mode,
)
from utilities import console
from utilities.constants import OS_FLAVOR_RHEL, TIMEOUT_8MIN, Images
from utilities.infra import create_ns
from utilities.storage import (
    check_upload_virtctl_result,
    create_dv,
    create_vm_from_dv,
    get_downloaded_artifact,
    virtctl_upload_dv,
    write_file,
)
from utilities.virt import running_vm


@pytest.fixture()
def imported_dv_in_progress_second_namespace(
    rhel9_http_image_url,
    namespace_for_backup2,
    storage_class_for_snapshot,
):
    with create_dv(
        dv_name="imported-dv",
        namespace=namespace_for_backup2.name,
        url=rhel9_http_image_url,
        size=Images.Rhel.DEFAULT_DV_SIZE,
        storage_class=storage_class_for_snapshot,
    ) as dv:
        yield dv


@pytest.fixture()
def imported_dv_second_namespace(imported_dv_in_progress_second_namespace):
    imported_dv_in_progress_second_namespace.wait_for_dv_success()
    yield imported_dv_in_progress_second_namespace


@pytest.fixture()
def namespace_for_backup():
    yield from create_ns(name="velero-test-ns")


@pytest.fixture()
def velero_backup_single_namespace(request, imported_dv_in_progress_second_namespace):
    with VeleroBackup(
        included_namespaces=[
            imported_dv_in_progress_second_namespace.namespace,
        ],
        name="backup-ns",
        wait_complete=request.param.get("wait_complete"),
    ) as backup:
        yield backup


@pytest.fixture()
def namespace_for_backup2():
    yield from create_ns(name="velero-test-ns2")


@pytest.fixture()
def velero_backup_multiple_namespaces(imported_dv_second_namespace, rhel_vm_with_data_volume_template):
    with VeleroBackup(
        included_namespaces=[
            imported_dv_second_namespace.namespace,
            rhel_vm_with_data_volume_template.namespace,
        ],
        name="backup-multiple-ns",
    ) as backup:
        yield backup


@pytest.fixture()
def velero_restore_multiple_namespaces(velero_backup_multiple_namespaces):
    # Delete NS in order to restore it
    for ns in velero_backup_multiple_namespaces.included_namespaces:
        Namespace(name=ns).delete(wait=True)
    with VeleroRestore(
        included_namespaces=velero_backup_multiple_namespaces.included_namespaces,
        name="restore-multiple-ns",
        backup_name=velero_backup_multiple_namespaces.name,
    ) as restore:
        yield restore


@pytest.fixture()
def rhel_vm_with_data_volume_template(
    request,
    namespace_for_backup,
    snapshot_storage_class_name_scope_module,
):
    volume_mode = request.param.get("volume_mode")
    if not is_storage_class_support_volume_mode(
        storage_class_name=snapshot_storage_class_name_scope_module,
        requested_volume_mode=volume_mode,
    ):
        pytest.skip(
            f"Storage class: {snapshot_storage_class_name_scope_module} don't support volume mode: {volume_mode}"
        )
    with create_rhel_vm(
        storage_class=snapshot_storage_class_name_scope_module,
        namespace=namespace_for_backup.name,
        dv_name=request.param.get("dv_name"),
        vm_name=request.param.get("vm_name"),
        wait_running=True,
        volume_mode=volume_mode,
        rhel_image=request.param.get("rhel_image"),
    ) as vm:
        write_file(
            vm=vm,
            filename=FILE_NAME_FOR_BACKUP,
            content=TEXT_TO_TEST,
            console_impl=console.RHEL,
            stop_vm=False,
        )
        yield vm


@pytest.fixture()
def velero_backup_first_namespace_using_datamover(namespace_for_backup):
    with VeleroBackup(
        included_namespaces=[
            namespace_for_backup.name,
        ],
        name="datamover-backup-ns",
        snapshot_move_data=True,
        storage_location="dpa-1",
    ) as backup:
        yield backup


@pytest.fixture()
def velero_restore_first_namespace_with_datamover(
    velero_backup_first_namespace_using_datamover,
):
    # Delete NS in order to restore it
    Namespace(name=velero_backup_first_namespace_using_datamover.included_namespaces[0]).delete(wait=True)
    with VeleroRestore(
        included_namespaces=velero_backup_first_namespace_using_datamover.included_namespaces,
        name="datamover-restore-ns",
        backup_name=velero_backup_first_namespace_using_datamover.name,
        timeout=TIMEOUT_8MIN,
    ) as restore:
        yield restore


@pytest.fixture()
def rhel_vm_from_existing_dv(imported_dv_second_namespace, stopped_vm):
    with create_vm_from_dv(
        dv=imported_dv_second_namespace,
        vm_name="rhel-vm-from-existing-dv",
        start=True,
        os_flavor=OS_FLAVOR_RHEL,
        memory_requests=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=True)
        write_file(
            vm=vm,
            filename=FILE_NAME_FOR_BACKUP,
            content=TEXT_TO_TEST,
            console_impl=console.RHEL,
            stop_vm=stopped_vm,
        )
        yield vm


@pytest.fixture(scope="module")
def oadp_tmp_directory(tmpdir_factory):
    return tmpdir_factory.mktemp("oadp_upload").join(Images.Rhel.RHEL9_3_IMG)


@pytest.fixture(scope="module")
def downloaded_rhel_image(oadp_tmp_directory):
    get_downloaded_artifact(
        remote_name=f"{Images.Rhel.DIR}/{Images.Rhel.RHEL9_3_IMG}",
        local_name=oadp_tmp_directory,
    )


@pytest.fixture()
def cloned_rhel_dv(imported_dv_second_namespace):
    with create_dv(
        source="pvc",
        dv_name="cloned-dv",
        namespace=imported_dv_second_namespace.namespace,
        size=imported_dv_second_namespace.size,
        source_pvc=imported_dv_second_namespace.name,
        storage_class=imported_dv_second_namespace.storage_class,
    ) as cdv:
        cdv.wait_for_dv_success()
        yield cdv


@pytest.fixture()
def uploaded_rhel_dv(
    namespace_for_backup2,
    storage_class_for_snapshot,
    oadp_tmp_directory,
    downloaded_rhel_image,
):
    dv_name = "uploaded-dv"
    with virtctl_upload_dv(
        namespace=namespace_for_backup2.name,
        name=dv_name,
        size=Images.Rhel.DEFAULT_DV_SIZE,
        image_path=oadp_tmp_directory,
        storage_class=storage_class_for_snapshot,
        insecure=True,
    ) as res:
        check_upload_virtctl_result(result=res)
        yield DataVolume(namespace=namespace_for_backup2.name, name=dv_name)


@pytest.fixture()
def velero_backup_second_namespace_using_datamover(namespace_for_backup2):
    with VeleroBackup(
        included_namespaces=[
            namespace_for_backup2.name,
        ],
        name="datamover-backup-ns2",
        snapshot_move_data=True,
        storage_location="dpa-1",
    ) as backup:
        yield backup


@pytest.fixture()
def velero_restore_second_namespace_with_datamover(
    velero_backup_second_namespace_using_datamover,
):
    # Delete NS in order to restore it
    Namespace(name=velero_backup_second_namespace_using_datamover.included_namespaces[0]).delete(wait=True)
    with VeleroRestore(
        included_namespaces=velero_backup_second_namespace_using_datamover.included_namespaces,
        name="datamover-restore-ns2",
        backup_name=velero_backup_second_namespace_using_datamover.name,
        timeout=TIMEOUT_8MIN,
    ) as restore:
        yield restore


@pytest.fixture()
def stopped_vm(request):
    return request.param.get("stopped_vm")
