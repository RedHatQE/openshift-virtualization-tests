import logging

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
from utilities.constants.pytest import UNPRIVILEGED_USER
from utilities.constants.storage import BIND_IMMEDIATE_ANNOTATION, CDI_CLONE_SOURCER_CLUSTER_ROLE, REGISTRY_STR
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
def validation_os_images_role_binding(admin_client, validation_os_images_namespace):
    """Grants the unprivileged user permission to clone from the validation-os-images namespace.

    Binds the CDI-shipped ``cdi.kubevirt.io:clone-sourcer`` ClusterRole to the unprivileged user in the
    validation-os-images namespace.

    Yields:
        RoleBinding: The RoleBinding granting clone-sourcer permission to the unprivileged user.
    """
    role_binding = RoleBinding(
        client=admin_client,
        name="validation-os-images-clone-sourcer",
        namespace=validation_os_images_namespace.name,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        role_ref_kind=ClusterRole.kind,
        role_ref_name=CDI_CLONE_SOURCER_CLUSTER_ROLE,
    )

    if role_binding.exists:
        LOGGER.info(f"Reusing existing RoleBinding {role_binding.name} in {role_binding.namespace}")
        subjects = role_binding.instance.subjects
        assert len(subjects) == 1, f"RoleBinding {role_binding.name} has {len(subjects)} subjects, expected exactly one"
        subject = subjects[0]
        assert subject.kind == "User", f"RoleBinding {role_binding.name} subject kind is {subject.kind}, expected User"
        assert subject.name == UNPRIVILEGED_USER, (
            f"RoleBinding {role_binding.name} subject name is {subject.name}, expected {UNPRIVILEGED_USER}"
        )
        role_ref = role_binding.instance.roleRef
        assert role_ref.kind == ClusterRole.kind, (
            f"RoleBinding {role_binding.name} roleRef kind is {role_ref.kind}, expected {ClusterRole.kind}"
        )
        assert role_ref.name == CDI_CLONE_SOURCER_CLUSTER_ROLE, (
            f"RoleBinding {role_binding.name} roleRef name is {role_ref.name}, expected {CDI_CLONE_SOURCER_CLUSTER_ROLE}"
        )
        yield role_binding
        return

    LOGGER.info(
        f"Creating RoleBinding {role_binding.name} in {role_binding.namespace} "
        f"binding {CDI_CLONE_SOURCER_CLUSTER_ROLE} to user {UNPRIVILEGED_USER}"
    )
    with role_binding as clone_sourcer_role_binding:
        yield clone_sourcer_role_binding


@pytest.fixture(scope="module")
def validation_os_images_clone_role_binding_for_namespace(admin_client, namespace, validation_os_images_namespace):
    """Grants a test namespace's default ServiceAccount permission to clone from validation-os-images.

    A VM created with a cross-namespace ``dataVolumeTemplates`` clone has its clone DataVolume created by the
    virt-controller, which authorizes the clone against the VM namespace's ``default`` ServiceAccount rather
    than the interactive user. This binds the CDI-shipped ``cdi.kubevirt.io:clone-sourcer`` ClusterRole to that
    ServiceAccount in the validation-os-images namespace, granting the ``datavolumes/source`` permission the
    ``datavolume-mutate.cdi.kubevirt.io`` webhook requires. Tests that clone the image by creating the
    DataVolume directly (as the unprivileged user) are covered by ``validation_os_images_role_binding`` instead.

    Yields:
        RoleBinding: The RoleBinding granting clone-sourcer permission to the test namespace's default SA.
    """
    role_binding = RoleBinding(
        client=admin_client,
        name=f"clone-sourcer-{namespace.name}",
        namespace=validation_os_images_namespace.name,
        subjects_kind="ServiceAccount",
        subjects_name="default",
        subjects_namespace=namespace.name,
        role_ref_kind=ClusterRole.kind,
        role_ref_name=CDI_CLONE_SOURCER_CLUSTER_ROLE,
    )

    if role_binding.exists:
        LOGGER.warning(
            f"Deleting leftover RoleBinding {role_binding.name} in {role_binding.namespace} from a previous run"
        )
        role_binding.delete(wait=True)

    LOGGER.info(
        f"Creating RoleBinding {role_binding.name} in {role_binding.namespace} binding "
        f"{CDI_CLONE_SOURCER_CLUSTER_ROLE} to the default ServiceAccount of namespace {namespace.name}"
    )
    with role_binding as clone_sourcer_role_binding:
        yield clone_sourcer_role_binding


@pytest.fixture(scope="session")
def windows_validation_os_images_data_volume_scope_session(
    validation_os_images_namespace,
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
