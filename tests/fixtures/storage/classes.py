import logging

import pytest
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_class import StorageClass
from pytest_testconfig import config as py_config

from utilities.constants.storage import StorageClassNames
from utilities.pytest_utils import exit_pytest_execution
from utilities.storage import (
    get_default_storage_class,
    get_storage_class_with_specified_volume_mode,
    is_snapshot_supported_by_sc,
    remove_default_storage_classes,
    update_default_sc,
    verify_boot_sources_reimported,
)

LOGGER = logging.getLogger(__name__)

RWX_FS_STORAGE_CLASS_NAMES_LIST = [
    StorageClassNames.CEPHFS,
    StorageClassNames.TRIDENT_CSI_FSX,
    StorageClassNames.PORTWORX_CSI_DB_SHARED,
]


@pytest.fixture(scope="session")
def cluster_storage_classes(admin_client):
    return list(StorageClass.get(client=admin_client))


@pytest.fixture(scope="session")
def cluster_storage_classes_names(cluster_storage_classes):
    return [sc.name for sc in cluster_storage_classes]


@pytest.fixture(scope="session")
def default_sc(admin_client):
    """
    Get default Storage Class defined
    """
    try:
        yield get_default_storage_class(client=admin_client)
    except ValueError:
        yield


@pytest.fixture(scope="session")
def available_storage_classes_names():
    return [[*sc][0] for sc in py_config["storage_class_matrix"]]


@pytest.fixture(scope="session")
def ocs_storage_class(cluster_storage_classes):
    """
    Get the OCS storage class if configured
    """
    for sc in cluster_storage_classes:
        if sc.name == StorageClassNames.CEPH_RBD_VIRTUALIZATION:
            return sc


@pytest.fixture(scope="session")
def skip_test_if_no_ocs_sc(ocs_storage_class):
    """
    Skip test if no OCS storage class available
    """
    if not ocs_storage_class:
        pytest.skip("Skipping test, OCS storage class is not deployed")


@pytest.fixture(scope="session")
def ocs_current_version(ocs_storage_class, admin_client):
    if ocs_storage_class:
        for csv in ClusterServiceVersion.get(
            client=admin_client,
            namespace="openshift-storage",
            label_selector=f"{ClusterServiceVersion.ApiGroup.OPERATORS_COREOS_COM}/ocs-operator.openshift-storage",
        ):
            return csv.instance.spec.version


@pytest.fixture(scope="session")
def storage_class_for_snapshot(admin_client):
    available_storage_classes = py_config["storage_class_matrix"]
    sc_for_snapshot = None
    sc_names = []
    for sc in available_storage_classes:
        sc_name = [*sc][0]
        if is_snapshot_supported_by_sc(sc_name=sc_name, client=admin_client):
            sc_for_snapshot = sc_name
            LOGGER.info(f"Storage class for snapshot: {sc_for_snapshot}")
            break
        sc_names.append(sc_name)
    if not sc_for_snapshot:
        LOGGER.warning(f"No Storage class among {sc_names} supports snapshots")
    yield sc_for_snapshot


@pytest.fixture(scope="session")
def skip_if_no_storage_class_for_snapshot(storage_class_for_snapshot):
    if not storage_class_for_snapshot:
        sc_names = [[*sc][0] for sc in py_config["storage_class_matrix"]]
        pytest.skip(f"There's no Storage Class among {sc_names} that supports snapshots, skipping the test")


@pytest.fixture(scope="session")
def storage_class_with_filesystem_volume_mode(available_storage_classes_names):
    yield get_storage_class_with_specified_volume_mode(
        volume_mode=DataVolume.VolumeMode.FILE, sc_names=available_storage_classes_names
    )


@pytest.fixture(scope="session")
def storage_class_with_block_volume_mode(available_storage_classes_names):
    yield get_storage_class_with_specified_volume_mode(
        volume_mode=DataVolume.VolumeMode.BLOCK,
        sc_names=available_storage_classes_names,
    )


@pytest.fixture(scope="module")
def skip_test_if_no_block_sc(storage_class_with_block_volume_mode):
    if not storage_class_with_block_volume_mode:
        pytest.skip("Skip the test: no Storage class with Block volume mode")


@pytest.fixture()
def removed_default_storage_classes(admin_client, golden_images_namespace, cluster_storage_classes):
    with remove_default_storage_classes(cluster_storage_classes=cluster_storage_classes):
        yield
    if not verify_boot_sources_reimported(admin_client=admin_client, namespace=golden_images_namespace.name):
        pytest.fail("Failed to reimport all boot sources at teardown")


@pytest.fixture(scope="module")
def snapshot_storage_class_name_scope_module(
    storage_class_matrix_snapshot_matrix__module__,
):
    return [*storage_class_matrix_snapshot_matrix__module__][0]


@pytest.fixture(scope="session")
def updated_default_storage_class_ocs_virt(
    admin_client,
    upgrade_skip_default_sc_setup,
    cluster_storage_classes,
    available_storage_classes_names,
    ocs_storage_class,
    golden_images_namespace,
):
    # set ocs-virt as default storage class if it isn't
    if (
        not upgrade_skip_default_sc_setup
        and ocs_storage_class
        and ocs_storage_class.name in available_storage_classes_names
        and ocs_storage_class.instance.metadata.get("annotations", {}).get(
            StorageClass.Annotations.IS_DEFAULT_VIRT_CLASS
        )
        != "true"
    ):
        boot_source_imported_successfully = False
        with remove_default_storage_classes(cluster_storage_classes=cluster_storage_classes):
            with update_default_sc(default=True, storage_class=ocs_storage_class):
                boot_source_imported_successfully = verify_boot_sources_reimported(
                    admin_client=admin_client,
                    namespace=golden_images_namespace.name,
                )
                if boot_source_imported_successfully:
                    yield

        # on teardown, wait for the original sources to re-create
        verify_boot_sources_reimported(
            admin_client=admin_client,
            namespace=golden_images_namespace.name,
        )
        if not boot_source_imported_successfully:
            exit_pytest_execution(
                admin_client=admin_client,
                log_message=f"Failed to set {ocs_storage_class.name} as default storage class",
                filename="default_storage_class_failure.txt",
            )
    else:
        yield


@pytest.fixture(scope="session")
def rwx_fs_available_storage_classes_names(cluster_storage_classes_names):
    return [
        storage_class
        for storage_class in cluster_storage_classes_names
        if storage_class in RWX_FS_STORAGE_CLASS_NAMES_LIST
    ]


@pytest.fixture()
def storage_class_name_scope_function(storage_class_matrix__function__):
    return [*storage_class_matrix__function__][0]
