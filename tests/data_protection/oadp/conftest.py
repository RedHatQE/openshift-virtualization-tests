import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.namespace import Namespace
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pytest_testconfig import config as py_config

from tests.data_protection.oadp.utils import (
    FILE_PATH_FOR_WINDOWS_BACKUP,
)
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_test_artifact_server_url,
)
from utilities.constants import (
    BACKUP_STORAGE_LOCATION,
    CONTAINER_DISK_IMAGE_PATH_STR,
    FILE_NAME_FOR_BACKUP,
    OS_FLAVOR_RHEL,
    OS_FLAVOR_WIN_CONTAINER_DISK,
    TEXT_TO_TEST,
    TIMEOUT_8MIN,
    TIMEOUT_15MIN,
    U1_LARGE,
    Images,
)
from utilities.infra import create_ns
from utilities.oadp import (
    VeleroBackup,
    VeleroRestore,
    create_rhel_vm,
    is_storage_class_support_volume_mode,
)
from utilities.storage import (
    check_upload_virtctl_result,
    create_dv,
    create_vm_from_dv,
    get_downloaded_artifact,
    virtctl_upload_dv,
    write_file,
    write_file_windows_vm,
)
from utilities.virt import VirtualMachineForTests, running_vm


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
        client=namespace_for_backup2.client,
    ) as dv:
        yield dv


@pytest.fixture()
def imported_dv_second_namespace(imported_dv_in_progress_second_namespace):
    imported_dv_in_progress_second_namespace.wait_for_dv_success()
    yield imported_dv_in_progress_second_namespace


@pytest.fixture()
def namespace_for_backup(admin_client):
    yield from create_ns(admin_client=admin_client, name="velero-test-ns")


@pytest.fixture()
def velero_backup_single_namespace(request, admin_client, imported_dv_in_progress_second_namespace):
    with VeleroBackup(
        client=admin_client,
        included_namespaces=[
            imported_dv_in_progress_second_namespace.namespace,
        ],
        name="backup-ns",
        wait_complete=request.param.get("wait_complete"),
    ) as backup:
        yield backup


@pytest.fixture()
def namespace_for_backup2(admin_client):
    yield from create_ns(admin_client=admin_client, name="velero-test-ns2")


@pytest.fixture()
def velero_backup_multiple_namespaces(admin_client, imported_dv_second_namespace, rhel_vm_with_data_volume_template):
    with VeleroBackup(
        client=admin_client,
        included_namespaces=[
            imported_dv_second_namespace.namespace,
            rhel_vm_with_data_volume_template.namespace,
        ],
        name="backup-multiple-ns",
    ) as backup:
        yield backup


@pytest.fixture()
def velero_restore_multiple_namespaces(admin_client, velero_backup_multiple_namespaces):
    # Delete NS in order to restore it
    for ns in velero_backup_multiple_namespaces.included_namespaces:
        Namespace(name=ns).delete(wait=True)
    with VeleroRestore(
        client=admin_client,
        included_namespaces=velero_backup_multiple_namespaces.included_namespaces,
        name="restore-multiple-ns",
        backup_name=velero_backup_multiple_namespaces.name,
    ) as restore:
        yield restore


@pytest.fixture()
def rhel_vm_with_data_volume_template(
    request,
    admin_client,
    namespace_for_backup,
    snapshot_storage_class_name_scope_module,
):
    volume_mode = request.param.get("volume_mode")
    if not is_storage_class_support_volume_mode(
        admin_client=admin_client,
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
        client=admin_client,
    ) as vm:
        write_file(
            vm=vm,
            filename=FILE_NAME_FOR_BACKUP,
            content=TEXT_TO_TEST,
            stop_vm=False,
        )
        yield vm


@pytest.fixture()
def windows_vm_with_data_volume_template(
    admin_client,
    namespace_for_backup,
    snapshot_storage_class_name_scope_module,
):
    """Windows 2022 VM with InstanceType and Preference in the backup namespace for OADP backup testing."""
    artifactory_secret = None
    artifactory_config_map = None

    try:
        artifactory_secret = get_artifactory_secret(namespace=namespace_for_backup.name)
        artifactory_config_map = get_artifactory_config_map(namespace=namespace_for_backup.name)

        dv = DataVolume(
            name="oadp-windows-dv",
            namespace=namespace_for_backup.name,
            storage_class=snapshot_storage_class_name_scope_module,
            source="registry",
            url=(
                f"{get_test_artifact_server_url(schema='registry')}/"
                f"{py_config['latest_windows_os_dict'][CONTAINER_DISK_IMAGE_PATH_STR]}"
            ),
            size=Images.Windows.CONTAINER_DISK_DV_SIZE,
            client=admin_client,
            api_name="storage",
            secret=artifactory_secret,
            cert_configmap=artifactory_config_map.name,
        )
        dv.to_dict()

        with VirtualMachineForTests(
            name="oadp-windows-vm",
            namespace=namespace_for_backup.name,
            client=admin_client,
            vm_instance_type=VirtualMachineClusterInstancetype(client=admin_client, name=U1_LARGE),
            vm_preference=VirtualMachineClusterPreference(client=admin_client, name="windows.2k22"),
            data_volume_template=dv.res,
            os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        ) as vm:
            running_vm(vm=vm)
            write_file_windows_vm(vm=vm, file_path=FILE_PATH_FOR_WINDOWS_BACKUP, content=TEXT_TO_TEST)
            yield vm
    finally:
        cleanup_artifactory_secret_and_config_map(
            artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
        )


@pytest.fixture()
def velero_backup_first_namespace_without_datamover(
    admin_client,
    namespace_for_backup,
    windows_vm_with_data_volume_template,
):
    with VeleroBackup(
        client=admin_client,
        included_namespaces=[
            namespace_for_backup.name,
        ],
        name="backup-windows-dvt-ns",
    ) as backup:
        yield backup


@pytest.fixture()
def velero_restore_first_namespace_without_datamover(
    admin_client,
    velero_backup_first_namespace_without_datamover,
):
    Namespace(name=velero_backup_first_namespace_without_datamover.included_namespaces[0]).delete(wait=True)
    with VeleroRestore(
        client=admin_client,
        included_namespaces=velero_backup_first_namespace_without_datamover.included_namespaces,
        name="restore-windows-dvt-ns",
        backup_name=velero_backup_first_namespace_without_datamover.name,
        timeout=TIMEOUT_8MIN,
    ) as restore:
        yield restore


@pytest.fixture()
def velero_backup_first_namespace_using_datamover(admin_client, namespace_for_backup):
    with VeleroBackup(
        client=admin_client,
        included_namespaces=[
            namespace_for_backup.name,
        ],
        name="datamover-backup-ns",
        snapshot_move_data=True,
        storage_location=BACKUP_STORAGE_LOCATION,
    ) as backup:
        yield backup


@pytest.fixture()
def velero_restore_first_namespace_with_datamover(
    admin_client,
    velero_backup_first_namespace_using_datamover,
):
    # Delete NS in order to restore it
    Namespace(name=velero_backup_first_namespace_using_datamover.included_namespaces[0]).delete(wait=True)
    with VeleroRestore(
        client=admin_client,
        included_namespaces=velero_backup_first_namespace_using_datamover.included_namespaces,
        name="datamover-restore-ns",
        backup_name=velero_backup_first_namespace_using_datamover.name,
        timeout=TIMEOUT_8MIN,
    ) as restore:
        yield restore


@pytest.fixture()
def rhel_vm_from_existing_dv(imported_dv_second_namespace):
    with create_vm_from_dv(
        dv=imported_dv_second_namespace,
        vm_name="rhel-vm-from-existing-dv",
        start=True,
        os_flavor=OS_FLAVOR_RHEL,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        client=imported_dv_second_namespace.client,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=True)
        write_file(
            vm=vm,
            filename=FILE_NAME_FOR_BACKUP,
            content=TEXT_TO_TEST,
            stop_vm=False,
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
        client=imported_dv_second_namespace.client,
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
        client=namespace_for_backup2.client,
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
def velero_backup_second_namespace_using_datamover(admin_client, namespace_for_backup2):
    with VeleroBackup(
        client=admin_client,
        included_namespaces=[
            namespace_for_backup2.name,
        ],
        name="datamover-backup-ns2",
        snapshot_move_data=True,
        storage_location=BACKUP_STORAGE_LOCATION,
    ) as backup:
        yield backup


@pytest.fixture()
def velero_restore_second_namespace_with_datamover(
    admin_client,
    velero_backup_second_namespace_using_datamover,
):
    # Delete NS in order to restore it
    Namespace(name=velero_backup_second_namespace_using_datamover.included_namespaces[0]).delete(wait=True)
    with VeleroRestore(
        client=admin_client,
        included_namespaces=velero_backup_second_namespace_using_datamover.included_namespaces,
        name="datamover-restore-ns2",
        backup_name=velero_backup_second_namespace_using_datamover.name,
        timeout=TIMEOUT_15MIN,
    ) as restore:
        yield restore
