"""
Restricted namespace cloning
"""

import logging

import pytest
from kubernetes.client.rest import ApiException

from tests.storage.constants import ADMIN_NAMESPACE_PARAM
from tests.storage.restricted_namespace_cloning.constants import (
    ALL,
    DATAVOLUMES,
    DATAVOLUMES_AND_DVS_SRC,
    DATAVOLUMES_SRC,
    DV_PARAMS,
    METADATA,
    PERMISSIONS_DST,
    PERMISSIONS_DST_SA,
    PERMISSIONS_SRC,
    PERMISSIONS_SRC_SA,
    SPEC,
    VERBS_DST,
    VERBS_DST_SA,
    VERBS_SRC,
    VERBS_SRC_SA,
    VM_FOR_TEST,
)
from tests.storage.restricted_namespace_cloning.utils import verify_snapshot_used_namespace_transfer
from utilities.constants import QUARANTINED, Images
from utilities.storage import ErrorMsg
from utilities.virt import VirtualMachineForTests

pytestmark = [
    pytest.mark.usefixtures("fail_when_no_unprivileged_client_available"),
    pytest.mark.post_upgrade,
]


LOGGER = logging.getLogger(__name__)


def get_dv_template(data_volume_clone_settings):
    return {
        METADATA: data_volume_clone_settings.res[METADATA],
        SPEC: data_volume_clone_settings.res[SPEC],
    }


def create_vm_negative(
    namespace,
    service_accounts,
    unprivileged_client,
    data_volume_clone_settings,
):
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with VirtualMachineForTests(
            name=VM_FOR_TEST,
            namespace=namespace,
            os_flavor=Images.Cirros.OS_FLAVOR,
            service_accounts=service_accounts,
            client=unprivileged_client,
            memory_guest=Images.Cirros.DEFAULT_MEMORY_SIZE,
            data_volume_template=get_dv_template(data_volume_clone_settings=data_volume_clone_settings),
        ):
            return


@pytest.mark.sno
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, perm_src_service_account, perm_destination_service_account",
    [
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            {PERMISSIONS_SRC_SA: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC_SA: ALL},
            {PERMISSIONS_DST_SA: DATAVOLUMES_AND_DVS_SRC, VERBS_DST_SA: ALL},
            marks=pytest.mark.polarion("CNV-2826"),
        )
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_create_vm_with_cloned_data_volume_positive(
    unprivileged_client,
    restricted_role_binding_for_vms_in_destination_namespace,
    data_volume_clone_settings,
    perm_src_service_account,
    perm_destination_service_account,
    permissions_pvc_destination,
    vm_for_restricted_namespace_cloning_test,
):
    verify_snapshot_used_namespace_transfer(
        cdv=data_volume_clone_settings,
        unprivileged_client=unprivileged_client,
    )


@pytest.mark.xfail(
    reason=f"{QUARANTINED}: fails since 4.19; CNV-63482",
    run=False,
)
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, "
    "permissions_datavolume_source, permissions_datavolume_destination",
    [
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_SRC, VERBS_SRC: ALL},
            {PERMISSIONS_DST: DATAVOLUMES, VERBS_DST: ALL},
            marks=pytest.mark.polarion("CNV-2828"),
        )
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_create_vm_with_cloned_data_volume_grant_unprivileged_client_permissions_negative(
    namespace,
    destination_namespace,
    restricted_namespace_service_account,
    unprivileged_client,
    restricted_role_binding_for_vms_in_destination_namespace,
    data_volume_clone_settings,
    permissions_datavolume_source,
    permissions_datavolume_destination,
):
    create_vm_negative(
        namespace=destination_namespace.name,
        service_accounts=[restricted_namespace_service_account.name],
        unprivileged_client=unprivileged_client,
        data_volume_clone_settings=data_volume_clone_settings,
    )


@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, perm_src_service_account, perm_destination_service_account",
    [
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            {PERMISSIONS_SRC_SA: DATAVOLUMES, VERBS_SRC_SA: ALL},
            {PERMISSIONS_DST_SA: DATAVOLUMES, VERBS_DST_SA: ALL},
            marks=pytest.mark.polarion("CNV-2827"),
        )
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_create_vm_cloned_data_volume_restricted_ns_service_account_no_clone_perm_negative(
    namespace,
    destination_namespace,
    restricted_namespace_service_account,
    unprivileged_client,
    data_volume_clone_settings,
    perm_src_service_account,
    perm_destination_service_account,
):
    create_vm_negative(
        namespace=destination_namespace.name,
        service_accounts=[restricted_namespace_service_account.name],
        unprivileged_client=unprivileged_client,
        data_volume_clone_settings=data_volume_clone_settings,
    )


@pytest.mark.gating
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module",
    [
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            marks=pytest.mark.polarion("CNV-2829"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_create_vm_with_cloned_data_volume_permissions_for_pods_positive(
    unprivileged_client,
    data_volume_clone_settings,
    permission_src_service_account_for_creating_pods,
    permission_destination_service_account_for_creating_pods,
    permissions_pvc_destination,
    vm_for_restricted_namespace_cloning_test,
):
    verify_snapshot_used_namespace_transfer(
        cdv=data_volume_clone_settings,
        unprivileged_client=unprivileged_client,
    )
