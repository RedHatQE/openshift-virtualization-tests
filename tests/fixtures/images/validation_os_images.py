import logging
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
from utilities.constants.storage import (
    BIND_IMMEDIATE_ANNOTATION,
    CDI_CLONE_SOURCE_CLUSTER_ROLE,
    REGISTRY_STR,
    VIEW_CLUSTER_ROLE,
)
from utilities.constants.timeouts import TIMEOUT_10MIN, TIMEOUT_50MIN
from utilities.constants.virt import WIN_2K22
from utilities.os_utils import get_windows_container_disk_path
from utilities.storage import construct_datavolume_source_dict, generate_data_source_dict

LOGGER = logging.getLogger(__name__)


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
def validation_os_images_role_bindings(admin_client, validation_os_images_namespace):
    """Grants unprivileged clients least-privilege permissions to clone from the validation-os-images namespace.

    Binds two granular built-in ClusterRoles to ``system:authenticated`` in the validation-os-images
    namespace so cross-namespace clones from this namespace succeed with the least-privilege set
    recommended to customers: ``view`` (read the source images) and ``cdi.kubevirt.io:clone-source``
    (clone the source PVCs).

    Yields:
        list[RoleBinding]: The RoleBindings granting view and clone-source permissions.
    """
    role_bindings = {
        cluster_role_name: RoleBinding(
            client=admin_client,
            name=f"validation-os-images-{cluster_role_name.split(':')[-1]}",
            namespace=validation_os_images_namespace.name,
            subjects_kind="Group",
            subjects_name="system:authenticated",
            role_ref_kind=ClusterRole.kind,
            role_ref_name=cluster_role_name,
        )
        for cluster_role_name in (VIEW_CLUSTER_ROLE, CDI_CLONE_SOURCE_CLUSTER_ROLE)
    }

    with ExitStack() as stack:
        for cluster_role_name, role_binding in role_bindings.items():
            if role_binding.exists:
                subjects = next(iter(role_binding.instance.subjects))
                assert subjects.kind == "Group", (
                    f"RoleBinding {role_binding.name} subjects kind is {subjects.kind}, expected Group"
                )
                assert subjects.name == "system:authenticated", (
                    f"RoleBinding {role_binding.name} subjects name is {subjects.name}, expected system:authenticated"
                )
                role_ref = role_binding.instance.roleRef
                assert role_ref.kind == ClusterRole.kind, (
                    f"RoleBinding {role_binding.name} roleRef kind is {role_ref.kind}, expected {ClusterRole.kind}"
                )
                assert role_ref.name == cluster_role_name, (
                    f"RoleBinding {role_binding.name} roleRef name is {role_ref.name}, expected {cluster_role_name}"
                )
            else:
                LOGGER.info(
                    f"Creating RoleBinding {role_binding.name} in {role_binding.namespace} "
                    f"binding {cluster_role_name} to system:authenticated"
                )
                stack.enter_context(cm=role_binding)
        yield list(role_bindings.values())


@pytest.fixture(scope="session")
def windows_validation_os_images_data_volume_scope_session(
    validation_os_images_namespace,
    validation_os_images_role_bindings,
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
        namespace=validation_os_images_namespace.name,
        client=validation_os_images_namespace.client,
    )

    if win_dv.exists:
        win_dv.wait_for_dv_success(timeout=TIMEOUT_1MINUTE)
        yield win_dv
        return

    assert not conformance_tests, (
        f"Windows image {win_dv.name} does not exist in namespace {validation_os_images_namespace.name}."
        " Self-validation requires the Windows image to be pre-created."
    )

    artifactory_secret = get_artifactory_secret(
        namespace=validation_os_images_namespace.name, client=validation_os_images_namespace.client
    )
    artifactory_config_map = get_artifactory_config_map(
        namespace=validation_os_images_namespace.name, client=validation_os_images_namespace.client
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

    try:
        with win_dv as wdv:
            wdv.wait_for_dv_success(timeout=TIMEOUT_50MIN)
            yield wdv
    finally:
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
