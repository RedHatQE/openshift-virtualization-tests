from contextlib import ExitStack

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
from utilities.storage import construct_datavolume_source_dict, generate_data_source_dict


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


VALIDATION_OS_IMAGES_CLONE_ROLE = "validation-os-images-clone"


@pytest.fixture(scope="session")
def validation_os_images_role_binding(admin_client, validation_os_images_namespace):
    """Grants view and datavolumes/source permissions so unprivileged clients can clone from this namespace."""
    clone_role = ClusterRole(
        client=admin_client,
        name=VALIDATION_OS_IMAGES_CLONE_ROLE,
        rules=[
            {
                "apiGroups": [""],
                "resources": ["pods", "persistentvolumeclaims", "services", "endpoints", "configmaps", "secrets"],
                "verbs": ["get", "list", "watch"],
            },
            {
                "apiGroups": [DataVolume.api_group],
                "resources": ["datavolumes", "datasources"],
                "verbs": ["get", "list", "watch"],
            },
            {
                "apiGroups": [DataVolume.api_group],
                "resources": ["datavolumes/source"],
                "verbs": ["create"],
            },
        ],
    )

    role_binding = RoleBinding(
        client=admin_client,
        name="validation-os-images-view",
        namespace=validation_os_images_namespace.name,
        subjects_kind="Group",
        subjects_name="system:authenticated",
        role_ref_kind=ClusterRole.kind,
        role_ref_name=VALIDATION_OS_IMAGES_CLONE_ROLE,
    )

    # A RoleBinding created by an older revision of this fixture may still point to a different
    # ClusterRole. Remove it (independently of the clone_role state) so it can be recreated with
    # the correct roleRef; otherwise recreating it below fails with a 409 AlreadyExists conflict.
    if role_binding.exists and role_binding.instance.roleRef.name != VALIDATION_OS_IMAGES_CLONE_ROLE:
        role_binding.clean_up(wait=True)

    # Create only the resources that are missing so pre-existing ones are left untouched.
    with ExitStack() as stack:
        if not clone_role.exists:
            stack.enter_context(clone_role)
        if not role_binding.exists:
            stack.enter_context(role_binding)
        yield role_binding


@pytest.fixture(scope="session")
def windows_validation_os_images_data_volume_scope_session(
    validation_os_images_role_binding,
    conformance_tests,
):
    """Provides the DV backing the Windows Server 2022 image in the validation-os-images namespace.

    Resolution order:
        1. DataVolume exists — waits for success, yields it.
        2. DataVolume does not exist — imports via Artifactory (fails on conformance runs), yields the new DataVolume.

    Yields:
        DataVolume: The DV containing the Windows 2022 image.
    """

    win_dv = DataVolume(
        name=WIN_2K22,
        namespace=validation_os_images_role_binding.namespace,
        client=validation_os_images_role_binding.client,
    )

    if win_dv.exists:
        win_dv.wait_for_dv_success(timeout=TIMEOUT_1MINUTE)
        yield win_dv
        return

    assert not conformance_tests, (
        f"Windows image {win_dv.name} does not exist in namespace {validation_os_images_role_binding.namespace}."
        " Self-validation requires the Windows image to be pre-created."
    )

    artifactory_secret = get_artifactory_secret(
        namespace=validation_os_images_role_binding.namespace, client=validation_os_images_role_binding.client
    )
    artifactory_config_map = get_artifactory_config_map(
        namespace=validation_os_images_role_binding.namespace, client=validation_os_images_role_binding.client
    )

    win_dv.storage_class = py_config["default_storage_class"]
    win_dv.source_dict = construct_datavolume_source_dict(
        source=REGISTRY_STR,
        url=f"{get_test_artifact_server_url(schema=REGISTRY_STR)}/{get_windows_container_disk_path(os_value=WIN_2K22)}",
        secret_name=artifactory_secret.name,
        cert_configmap_name=artifactory_config_map.name,
    )
    win_dv.size = Images.Windows.CONTAINER_DISK_DV_SIZE
    win_dv.api_name = "storage"
    win_dv.annotations = BIND_IMMEDIATE_ANNOTATION

    with win_dv as wdv:
        wdv.wait_for_dv_success(timeout=TIMEOUT_50MIN)
        yield wdv
    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret,
        artifactory_config_map=artifactory_config_map,
    )


@pytest.fixture(scope="session")
def windows_validation_os_images_data_source_scope_session(
    admin_client, windows_validation_os_images_data_volume_scope_session
):
    win_data_source = DataSource(
        name=windows_validation_os_images_data_volume_scope_session.name,
        namespace=windows_validation_os_images_data_volume_scope_session.namespace,
        client=admin_client,
    )
    if win_data_source.exists:
        source_pvc = win_data_source.instance.spec.source.pvc
        assert source_pvc.name == windows_validation_os_images_data_volume_scope_session.name, (
            f"DataSource {win_data_source.name} source PVC name is {source_pvc.name}, "
            f"expected {windows_validation_os_images_data_volume_scope_session.name}"
        )
        assert source_pvc.namespace == windows_validation_os_images_data_volume_scope_session.pvc.namespace, (
            f"DataSource {win_data_source.name} source PVC namespace is {source_pvc.namespace}, "
            f"expected {windows_validation_os_images_data_volume_scope_session.namespace}"
        )
        yield win_data_source
        return

    win_data_source._source = generate_data_source_dict(dv=windows_validation_os_images_data_volume_scope_session)
    with win_data_source as wds:
        wds.wait_for_condition(
            condition=wds.Condition.READY,
            status=wds.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield wds
