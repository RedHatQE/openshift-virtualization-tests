"""
Pytest conftest file for CNV Storage restricted namespace cloning tests
"""

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.resource import Resource
from ocp_resources.service_account import ServiceAccount

from tests.storage.restricted_namespace_cloning.constants import (
    CREATE,
    LIST_GET,
    PERMISSIONS_DST,
    PERMISSIONS_DST_SA,
    PERMISSIONS_SRC,
    PERMISSIONS_SRC_SA,
    PERSISTENT_VOLUME_CLAIMS,
    RBAC_AUTHORIZATION_API_GROUP,
    TARGET_DV,
    VERBS_DST,
    VERBS_DST_SA,
    VERBS_SRC,
    VERBS_SRC_SA,
    VM_FOR_TEST,
)
from tests.storage.utils import (
    create_cluster_role,
    create_role_binding,
    set_permissions,
)
from utilities.constants import PVC, UNPRIVILEGED_USER, Images
from utilities.infra import create_ns
from utilities.storage import create_dv
from utilities.virt import VirtualMachineForTests, running_vm


@pytest.fixture(scope="module")
def destination_namespace(admin_client):
    yield from create_ns(name="restricted-namespace-test-destination-namespace", admin_client=admin_client)


@pytest.fixture(scope="module")
def restricted_namespace_service_account(destination_namespace):
    with ServiceAccount(name="vm-service-account", namespace=destination_namespace.name) as sa:
        yield sa


@pytest.fixture(scope="module")
def cluster_role_for_creating_pods():
    with create_cluster_role(
        name="pod-creator",
        api_groups=[""],
        verbs=CREATE,
        permissions_to_resources=["pods"],
    ) as cluster_role_pod_creator:
        yield cluster_role_pod_creator


@pytest.fixture()
def data_volume_clone_settings(destination_namespace, data_volume_multi_storage_scope_module):
    storage_class = data_volume_multi_storage_scope_module.storage_class
    dv = DataVolume(
        name=f"{TARGET_DV}-{storage_class}",
        namespace=destination_namespace.name,
        source=PVC,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.name,
        source_namespace=data_volume_multi_storage_scope_module.namespace,
        storage_class=storage_class,
        api_name="storage",
    )
    dv.to_dict()
    return dv


@pytest.fixture()
def restricted_role_binding_for_vms_in_destination_namespace(destination_namespace):
    with create_role_binding(
        name="allow-unprivileged-client-to-run-vms-on-dst-ns",
        namespace=destination_namespace.name,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RBAC_AUTHORIZATION_API_GROUP,
        role_ref_kind=ClusterRole.kind,
        role_ref_name=f"{Resource.ApiGroup.KUBEVIRT_IO}:admin",
    ) as kubevirt_admin_unprivileged_user_role_binding:
        yield kubevirt_admin_unprivileged_user_role_binding


@pytest.fixture()
def perm_src_service_account(request, namespace, destination_namespace, restricted_namespace_service_account):
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        role_api_groups=[DataVolume.api_group],
        verbs=request.param[VERBS_SRC_SA],
        permissions_to_resources=request.param[PERMISSIONS_SRC_SA],
        binding_name="role-bind-src",
        namespace=namespace.name,
        subjects_kind=restricted_namespace_service_account.kind,
        subjects_name=restricted_namespace_service_account.name,
        subjects_namespace=destination_namespace.name,
    ):
        yield


@pytest.fixture()
def perm_destination_service_account(request, destination_namespace, restricted_namespace_service_account):
    with set_permissions(
        role_name="datavolume-cluster-role-dst",
        role_api_groups=[DataVolume.api_group],
        verbs=request.param[VERBS_DST_SA],
        permissions_to_resources=request.param[PERMISSIONS_DST_SA],
        binding_name="role-bind-dst",
        namespace=destination_namespace.name,
        subjects_kind=restricted_namespace_service_account.kind,
        subjects_name=restricted_namespace_service_account.name,
        subjects_namespace=destination_namespace.name,
    ):
        yield


@pytest.fixture(scope="module")
def fail_when_no_unprivileged_client_available(unprivileged_client):
    if not unprivileged_client:
        pytest.fail("No unprivileged_client available, failing the test")


@pytest.fixture()
def permissions_datavolume_source(request, namespace):
    with set_permissions(
        role_name="datavolume-cluster-role-source",
        role_api_groups=[DataVolume.api_group],
        verbs=request.param[VERBS_SRC],
        permissions_to_resources=request.param[PERMISSIONS_SRC],
        binding_name="role-bind-datavolume-source",
        namespace=namespace.name,
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RBAC_AUTHORIZATION_API_GROUP,
    ):
        yield


@pytest.fixture()
def permissions_datavolume_destination(request, destination_namespace):
    with set_permissions(
        role_name="datavolume-cluster-role-destination",
        role_api_groups=[DataVolume.api_group],
        verbs=request.param[VERBS_DST],
        permissions_to_resources=request.param[PERMISSIONS_DST],
        binding_name="role-bind-datavolume-destination",
        namespace=destination_namespace.name,
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RBAC_AUTHORIZATION_API_GROUP,
    ):
        yield


@pytest.fixture()
def permissions_pvc_source(namespace):
    with set_permissions(
        role_name="pvc-cluster-role-source",
        role_api_groups=[PersistentVolumeClaim.api_group],
        verbs=LIST_GET,
        permissions_to_resources=PERSISTENT_VOLUME_CLAIMS,
        binding_name="role-bind-pvc-source",
        namespace=namespace.name,
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RBAC_AUTHORIZATION_API_GROUP,
    ):
        yield


@pytest.fixture()
def permissions_pvc_destination(destination_namespace):
    with set_permissions(
        role_name="pvc-cluster-role-destination",
        role_api_groups=[PersistentVolumeClaim.api_group],
        verbs=LIST_GET,
        permissions_to_resources=PERSISTENT_VOLUME_CLAIMS,
        binding_name="role-bind-pvc-destination",
        namespace=destination_namespace.name,
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RBAC_AUTHORIZATION_API_GROUP,
    ):
        yield


@pytest.fixture()
def permission_src_service_account_for_creating_pods(
    namespace,
    destination_namespace,
    restricted_namespace_service_account,
    cluster_role_for_creating_pods,
):
    with create_role_binding(
        name="service-account-can-create-pods-on-src",
        namespace=namespace.name,
        subjects_kind=restricted_namespace_service_account.kind,
        subjects_name=restricted_namespace_service_account.name,
        role_ref_kind=cluster_role_for_creating_pods.kind,
        role_ref_name=cluster_role_for_creating_pods.name,
        subjects_namespace=destination_namespace.name,
    ):
        yield


@pytest.fixture()
def permission_destination_service_account_for_creating_pods(
    destination_namespace, restricted_namespace_service_account, cluster_role_for_creating_pods
):
    with create_role_binding(
        name="service-account-can-create-pods-on-destination",
        namespace=destination_namespace.name,
        subjects_kind=restricted_namespace_service_account.kind,
        subjects_name=restricted_namespace_service_account.name,
        role_ref_kind=cluster_role_for_creating_pods.kind,
        role_ref_name=cluster_role_for_creating_pods.name,
        subjects_namespace=destination_namespace.name,
    ):
        yield


@pytest.fixture()
def dv_cloned_by_unprivileged_user_in_the_same_namespace(
    request,
    storage_class_name_scope_module,
    data_volume_multi_storage_scope_module,
    unprivileged_client,
    permissions_datavolume_source,
):
    namespace = data_volume_multi_storage_scope_module.namespace
    with create_dv(
        dv_name=f"{request.param['dv_name']}-{storage_class_name_scope_module}",
        namespace=namespace,
        source=PVC,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.pvc.name,
        source_namespace=namespace,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
    ) as cdv:
        yield cdv


@pytest.fixture()
def dv_destination_cloned_from_pvc(
    request,
    storage_class_name_scope_module,
    data_volume_multi_storage_scope_module,
    destination_namespace,
    unprivileged_client,
    permissions_datavolume_source,
    permissions_datavolume_destination,
):
    with create_dv(
        dv_name=f"{request.param['dv_name']}-{storage_class_name_scope_module}",
        namespace=destination_namespace.name,
        source=PVC,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.pvc.name,
        source_namespace=data_volume_multi_storage_scope_module.namespace,
        client=unprivileged_client,
        storage_class=storage_class_name_scope_module,
    ) as cdv:
        cdv.wait_for_dv_success()
        yield cdv


@pytest.fixture()
def vm_for_restricted_namespace_cloning_test(
    destination_namespace,
    restricted_namespace_service_account,
    unprivileged_client,
    restricted_role_binding_for_vms_in_destination_namespace,
    data_volume_clone_settings,
):
    with VirtualMachineForTests(
        name=VM_FOR_TEST,
        namespace=destination_namespace.name,
        os_flavor=Images.Cirros.OS_FLAVOR,
        service_accounts=[restricted_namespace_service_account.name],
        client=unprivileged_client,
        memory_guest=Images.Cirros.DEFAULT_MEMORY_SIZE,
        data_volume_template=data_volume_clone_settings.res,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False)
        yield vm


@pytest.fixture()
def user_has_get_permissions_in_source_namespace(
    namespace, unprivileged_client, data_volume_multi_storage_scope_module
):
    _ = DataVolume(
        namespace=namespace.name, name=data_volume_multi_storage_scope_module.name, client=unprivileged_client
    ).instance


@pytest.fixture()
def requested_verify_image_permissions(request):
    return request.param.get("verify_image_permissions")
