"""
Pytest conftest file for CNV Storage restricted namespace cloning tests
"""

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import Resource
from ocp_resources.service_account import ServiceAccount

from tests.storage.restricted_namespace_cloning.constants import (
    CREATE,
    PERMISSIONS_DST,
    PERMISSIONS_DST_SA,
    PERMISSIONS_SRC,
    PERMISSIONS_SRC_SA,
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
from utilities.constants import OS_FLAVOR_CIRROS, PVC, UNPRIVILEGED_USER, Images
from utilities.infra import create_ns
from utilities.storage import create_dv
from utilities.virt import VirtualMachineForTests, running_vm


@pytest.fixture(scope="module")
def destination_ns(unprivileged_client):
    yield from create_ns(name="restricted-namespace-destination-namespace", unprivileged_client=unprivileged_client)


@pytest.fixture(scope="module")
def restricted_namespace_service_account(destination_ns):
    with ServiceAccount(name="vm-service-account", namespace=destination_ns.name) as sa:
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
def data_volume_clone_settings(destination_ns, data_volume_multi_storage_scope_module):
    storage_class = data_volume_multi_storage_scope_module.storage_class
    dv = DataVolume(
        name=f"{TARGET_DV}-{storage_class}",
        namespace=destination_ns.name,
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
def restricted_role_binding_for_vms_in_destination_namespace(destination_ns):
    with create_role_binding(
        name="allow-unprivileged-client-to-run-vms-on-dst-ns",
        namespace=destination_ns.name,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RBAC_AUTHORIZATION_API_GROUP,
        role_ref_kind=ClusterRole.kind,
        role_ref_name=f"{Resource.ApiGroup.KUBEVIRT_IO}:admin",
    ) as kubevirt_admin_unprivileged_user_role_binding:
        yield kubevirt_admin_unprivileged_user_role_binding


@pytest.fixture()
def perm_src_service_account(request, namespace, destination_ns, restricted_namespace_service_account):
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        verbs=request.param[VERBS_SRC_SA],
        permissions_to_resources=request.param[PERMISSIONS_SRC_SA],
        binding_name="role-bind-src",
        namespace=namespace.name,
        subjects_kind=restricted_namespace_service_account.kind,
        subjects_name=restricted_namespace_service_account.name,
        subjects_namespace=destination_ns.name,
    ):
        yield


@pytest.fixture()
def perm_destination_service_account(request, destination_ns, restricted_namespace_service_account):
    with set_permissions(
        role_name="datavolume-cluster-role-dst",
        verbs=request.param[VERBS_DST_SA],
        permissions_to_resources=request.param[PERMISSIONS_DST_SA],
        binding_name="role-bind-dst",
        namespace=destination_ns.name,
        subjects_kind=restricted_namespace_service_account.kind,
        subjects_name=restricted_namespace_service_account.name,
        subjects_namespace=destination_ns.name,
    ):
        yield


@pytest.fixture(scope="module")
def skip_when_no_unprivileged_client_available(unprivileged_client):
    if not unprivileged_client:
        pytest.skip("No unprivileged client available, skipping test")


@pytest.fixture()
def permissions_src(request, namespace):
    with set_permissions(
        role_name="datavolume-cluster-role-src",
        verbs=request.param[VERBS_SRC],
        permissions_to_resources=request.param[PERMISSIONS_SRC],
        binding_name="role-bind-src",
        namespace=namespace.name,
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RBAC_AUTHORIZATION_API_GROUP,
    ):
        yield


@pytest.fixture()
def permissions_destination(request, destination_ns):
    with set_permissions(
        role_name="datavolume-cluster-role-destination",
        verbs=request.param[VERBS_DST],
        permissions_to_resources=request.param[PERMISSIONS_DST],
        binding_name="role-bind-destination",
        namespace=destination_ns.name,
        subjects_name=UNPRIVILEGED_USER,
        subjects_api_group=RBAC_AUTHORIZATION_API_GROUP,
    ):
        yield


@pytest.fixture()
def permission_src_service_account_for_creating_pods(
    namespace,
    destination_ns,
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
        subjects_namespace=destination_ns.name,
    ):
        yield


@pytest.fixture()
def permission_destination_service_account_for_creating_pods(
    destination_ns, restricted_namespace_service_account, cluster_role_for_creating_pods
):
    with create_role_binding(
        name="service-account-can-create-pods-on-destination",
        namespace=destination_ns.name,
        subjects_kind=restricted_namespace_service_account.kind,
        subjects_name=restricted_namespace_service_account.name,
        role_ref_kind=cluster_role_for_creating_pods.kind,
        role_ref_name=cluster_role_for_creating_pods.name,
        subjects_namespace=destination_ns.name,
    ):
        yield


@pytest.fixture()
def dv_cloned_by_unprivileged_user_in_the_same_namespace(
    request,
    storage_class_name_scope_module,
    data_volume_multi_storage_scope_module,
    unprivileged_client,
    permissions_src,
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
        cdv.wait_for_dv_success()
        yield cdv


@pytest.fixture()
def dv_destination_cloned_from_pvc(
    request,
    storage_class_name_scope_module,
    data_volume_multi_storage_scope_module,
    destination_ns,
    unprivileged_client,
    permissions_src,
    permissions_destination,
):
    with create_dv(
        dv_name=f"{request.param['dv_name']}-{storage_class_name_scope_module}",
        namespace=destination_ns.name,
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
    destination_ns,
    restricted_namespace_service_account,
    unprivileged_client,
    restricted_role_binding_for_vms_in_destination_namespace,
    data_volume_clone_settings,
):
    with VirtualMachineForTests(
        name=VM_FOR_TEST,
        namespace=destination_ns.name,
        os_flavor=OS_FLAVOR_CIRROS,
        service_accounts=[restricted_namespace_service_account.name],
        client=unprivileged_client,
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
        data_volume_template=data_volume_clone_settings.res,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False)
        yield vm
