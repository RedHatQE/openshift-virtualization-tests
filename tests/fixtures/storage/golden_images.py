import logging

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.data_source import DataSource
from ocp_resources.namespace import Namespace
from ocp_resources.role_binding import RoleBinding
from pytest_testconfig import config as py_config

from utilities.constants.components import RHEL9_STR
from utilities.ssp import get_data_import_crons
from utilities.storage import create_or_update_data_source, data_volume

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def golden_images_namespace(
    admin_client,
):
    for ns in Namespace.get(
        name=py_config["golden_images_namespace"],
        client=admin_client,
    ):
        return ns


@pytest.fixture(scope="session")
def golden_images_cluster_role_edit(
    admin_client,
):
    for cluster_role in ClusterRole.get(
        name="os-images.kubevirt.io:edit",
        client=admin_client,
    ):
        return cluster_role


@pytest.fixture()
def golden_images_edit_rolebinding(
    golden_images_namespace,
    golden_images_cluster_role_edit,
):
    with RoleBinding(
        name="role-bind-create-dv",
        namespace=golden_images_namespace.name,
        subjects_kind="User",
        subjects_name="unprivileged-user",
        subjects_namespace=golden_images_namespace.name,
        role_ref_kind=golden_images_cluster_role_edit.kind,
        role_ref_name=golden_images_cluster_role_edit.name,
    ) as role_binding:
        yield role_binding


@pytest.fixture()
def golden_image_data_volume_multi_storage_scope_function(
    admin_client,
    request,
    golden_images_namespace,
    storage_class_matrix__function__,
):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__function__,
        check_dv_exists=True,
        client=admin_client,
    )


@pytest.fixture()
def golden_image_data_source_multi_storage_scope_function(
    admin_client, golden_image_data_volume_multi_storage_scope_function
):
    yield from create_or_update_data_source(
        admin_client=admin_client,
        dv=golden_image_data_volume_multi_storage_scope_function,
    )


@pytest.fixture(scope="module")
def golden_image_data_volume_scope_module(request, admin_client, golden_images_namespace):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class=request.param["storage_class"],
        check_dv_exists=True,
        client=admin_client,
    )


@pytest.fixture()
def golden_image_data_volume_scope_function(request, admin_client, golden_images_namespace):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class=request.param["storage_class"],
        check_dv_exists=True,
        client=admin_client,
    )


@pytest.fixture()
def golden_image_data_source_scope_function(admin_client, golden_image_data_volume_scope_function):
    yield from create_or_update_data_source(admin_client=admin_client, dv=golden_image_data_volume_scope_function)


@pytest.fixture(scope="session")
def rhel9_data_source_scope_session(golden_images_namespace):
    return DataSource(
        client=golden_images_namespace.client,
        name=RHEL9_STR,
        namespace=golden_images_namespace.name,
        ensure_exists=True,
    )


@pytest.fixture(scope="session")
def rhel10_data_source_scope_session(golden_images_namespace):
    return DataSource(
        namespace=golden_images_namespace.name,
        name="rhel10",
        client=golden_images_namespace.client,
        ensure_exists=True,
    )


@pytest.fixture()
def golden_images_data_import_crons_scope_function(admin_client, golden_images_namespace):
    return get_data_import_crons(admin_client=admin_client, namespace=golden_images_namespace)


@pytest.fixture(scope="class")
def golden_images_data_import_crons_scope_class(admin_client, golden_images_namespace):
    return get_data_import_crons(admin_client=admin_client, namespace=golden_images_namespace)
