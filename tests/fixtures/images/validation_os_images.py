import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.namespace import Namespace
from ocp_resources.role_binding import RoleBinding
from ocp_resources.utils.constants import TIMEOUT_1MINUTE
from pytest_testconfig import config as py_config

from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_test_artifact_server_url,
)
from utilities.constants import Images
from utilities.constants.storage import BIND_IMMEDIATE_ANNOTATION, REGISTRY_STR
from utilities.constants.timeouts import TIMEOUT_10MIN, TIMEOUT_50MIN
from utilities.constants.virt import WIN_2K22
from utilities.os_utils import get_windows_container_disk_path
from utilities.storage import (
    generate_data_source_dict,
)


@pytest.fixture(scope="session")
def validation_os_images_namespace(admin_client):
    validation_os_images_namespace = Namespace(
        name="validation-os-images",
        client=admin_client,
    )
    if validation_os_images_namespace.exists:
        yield validation_os_images_namespace
    else:
        with validation_os_images_namespace as ns:
            yield ns


@pytest.fixture(scope="session")
def validation_os_images_role_binding(admin_client, validation_os_images_namespace):
    """Grants view permissions in the namespace so unprivileged clients can clone from it."""
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
):
    """
    Fixture that imports a Windows image into the validation os images namespace. Yields existing DataVolume if it was already created

    The DV is also used in self-validation and if we move the version, UI needs to follow.
    """

    win_dv = DataVolume(
        name=WIN_2K22,
        namespace=validation_os_images_role_binding.namespace,
        client=validation_os_images_role_binding.client,
    )
    if win_dv.exists:
        win_dv.wait_for_dv_success(timeout=TIMEOUT_1MINUTE)
        yield win_dv
    else:
        assert not py_config.get("conformance_tests"), (
            f"Windows image {WIN_2K22} does not exist in namespace {validation_os_images_role_binding.namespace}. Self-validation requires the Windows image to be pre-created."
        )

        artifactory_secret = get_artifactory_secret(
            namespace=validation_os_images_role_binding.namespace, client=validation_os_images_role_binding.client
        )
        artifactory_config_map = get_artifactory_config_map(
            namespace=validation_os_images_role_binding.namespace, client=validation_os_images_role_binding.client
        )
        try:
            with DataVolume(
                name=WIN_2K22,
                namespace=validation_os_images_role_binding.namespace,
                storage_class=py_config["default_storage_class"],
                source=REGISTRY_STR,
                url=f"{get_test_artifact_server_url(schema=REGISTRY_STR)}/{get_windows_container_disk_path(os_value=WIN_2K22)}",
                size=Images.Windows.CONTAINER_DISK_DV_SIZE,
                client=admin_client,
                api_name="storage",
                secret=artifactory_secret,
                cert_configmap=artifactory_config_map.name,
                annotations=BIND_IMMEDIATE_ANNOTATION,
            ) as wdv:
                wdv.wait_for_dv_success(timeout=TIMEOUT_50MIN)
                yield wdv
        finally:
            cleanup_artifactory_secret_and_config_map(
                artifactory_secret=artifactory_secret,
                artifactory_config_map=artifactory_config_map,
            )


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
    if not win_data_source.exists:
        win_data_source.deploy()

    win_data_source.wait_for_condition(
        condition=win_data_source.Condition.READY,
        status=win_data_source.Condition.Status.TRUE,
        timeout=TIMEOUT_10MIN,
    )
    yield win_data_source
