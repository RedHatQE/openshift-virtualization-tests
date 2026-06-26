import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.namespace import Namespace
from ocp_resources.role_binding import RoleBinding
from pytest_testconfig import config as py_config

from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_test_artifact_server_url,
)
from utilities.constants import TIMEOUT_40MIN, WIN_2K22, Images
from utilities.os_utils import get_windows_container_disk_path
from utilities.storage import (
    create_dummy_first_consumer_pod,
    generate_data_source_dict,
    sc_volume_binding_mode_is_wffc,
)

VALIDATION_OS_IMAGES_NAMESPACE = "validation-os-images"


@pytest.fixture(scope="session")
def validation_os_images_namespace(admin_client):
    validation_os_images_namespace = Namespace(
        name=VALIDATION_OS_IMAGES_NAMESPACE,
        client=admin_client,
    )
    if validation_os_images_namespace.exists:
        yield validation_os_images_namespace
    else:
        with validation_os_images_namespace as ns:
            yield ns


@pytest.fixture(scope="session")
def validation_os_images_role_binding(admin_client, validation_os_images_namespace):
    """Grants view permissions in the windows image namespace so unprivileged clients can clone from it."""
    role_binding = RoleBinding(
        client=admin_client,
        name="validation-os-images-view",
        namespace=validation_os_images_namespace.name,
        subjects_kind="Group",
        subjects_name="system:authenticated",
        role_ref_kind=ClusterRole.kind,
        role_ref_name="view",
    )

    if role_binding.exists:
        yield role_binding
    else:
        with role_binding as rb:
            yield rb


@pytest.fixture(scope="session")
def windows_validation_os_images_data_volume_scope_session(
    admin_client,
    validation_os_images_role_binding,
    validation_os_images_namespace_artifactory_secret_and_configmap,
):
    """Fixture that imports a Windows DataVolume from registry into the windows image namespace if the golden image does not exist."""

    win_dv = DataVolume(
        name=WIN_2K22,
        namespace=validation_os_images_role_binding.namespace,
        storage_class=py_config["default_storage_class"],
        source="registry",
        url=f"{get_test_artifact_server_url(schema='registry')}/{get_windows_container_disk_path(os_value=WIN_2K22)}",
        size=Images.Windows.CONTAINER_DISK_DV_SIZE,
        client=admin_client,
        api_name="storage",
        secret=validation_os_images_namespace_artifactory_secret_and_configmap["secret"],
        cert_configmap=validation_os_images_namespace_artifactory_secret_and_configmap["config_map"].name,
    )

    if win_dv.exists:
        yield win_dv
    else:
        with win_dv as wdv:
            if sc_volume_binding_mode_is_wffc(sc=py_config["default_storage_class"], client=wdv.client):
                create_dummy_first_consumer_pod(pvc=wdv.pvc)
            yield wdv


@pytest.fixture(scope="session")
def windows_validation_os_images_data_source_scope_session(
    admin_client,
    windows_validation_os_images_data_volume_scope_session,
):
    win_data_source = DataSource(
        name=windows_validation_os_images_data_volume_scope_session.name,
        namespace=windows_validation_os_images_data_volume_scope_session.namespace,
        client=admin_client,
        source=generate_data_source_dict(dv=windows_validation_os_images_data_volume_scope_session),
    )
    if win_data_source.exists and any(
        condition.get("type") == win_data_source.Condition.READY
        and condition.get("status") == win_data_source.Condition.Status.TRUE
        for condition in win_data_source.instance.get("status", {}).get("conditions", [])
    ):
        yield win_data_source
    else:
        with win_data_source as win_ds:
            win_data_source.wait_for_condition(
                condition=win_data_source.Condition.READY,
                status=win_data_source.Condition.Status.TRUE,
                timeout=TIMEOUT_40MIN,
            )
            yield win_ds


@pytest.fixture(scope="session")
def validation_os_images_namespace_artifactory_secret_and_configmap(validation_os_images_role_binding):
    artifactory_secret = get_artifactory_secret(
        namespace=validation_os_images_role_binding.namespace, client=validation_os_images_role_binding.client
    )
    artifactory_config_map = get_artifactory_config_map(
        namespace=validation_os_images_role_binding.namespace, client=validation_os_images_role_binding.client
    )
    try:
        yield {"secret": artifactory_secret, "config_map": artifactory_config_map}
    finally:
        cleanup_artifactory_secret_and_config_map(
            artifactory_secret=artifactory_secret,
            artifactory_config_map=artifactory_config_map,
        )
