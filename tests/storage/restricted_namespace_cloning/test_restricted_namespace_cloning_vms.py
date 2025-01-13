"""
Restricted namespace cloning
"""

import logging

import pytest
from kubernetes.client.rest import ApiException

from tests.storage.constants import NAMESPACE_PARAMS
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
from tests.storage.utils import (
    create_vm_and_verify_image_permission,
    verify_snapshot_used_namespace_transfer,
)
from utilities.constants import OS_FLAVOR_CIRROS, Images
from utilities.storage import ErrorMsg
from utilities.virt import VirtualMachineForTests

pytestmark = [
    pytest.mark.usefixtures("skip_when_no_unprivileged_client_available"),
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
            os_flavor=OS_FLAVOR_CIRROS,
            service_accounts=service_accounts,
            client=unprivileged_client,
            memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
            data_volume_template=get_dv_template(data_volume_clone_settings=data_volume_clone_settings),
        ):
            return


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_module, perm_src_service_account, perm_destination_service_account",
    [
        pytest.param(
            DV_PARAMS,
            {PERMISSIONS_SRC_SA: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC_SA: ALL},
            {PERMISSIONS_DST_SA: DATAVOLUMES_AND_DVS_SRC, VERBS_DST_SA: ALL},
            marks=pytest.mark.polarion("CNV-2826"),
        )
    ],
    indirect=True,
)
def test_create_vm_with_cloned_data_volume_positive(
    unprivileged_client,
    restricted_role_binding_for_vms_in_destination_namespace,
    data_volume_clone_settings,
    perm_src_service_account,
    perm_destination_service_account,
    vm_for_restricted_namespace_cloning_test,
):
    verify_snapshot_used_namespace_transfer(
        cdv=data_volume_clone_settings,
        unprivileged_client=unprivileged_client,
    )


@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, permissions_src, permissions_destination",
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_SRC, VERBS_SRC: ALL},
            {PERMISSIONS_DST: DATAVOLUMES, VERBS_DST: ALL},
            marks=pytest.mark.polarion("CNV-2828"),
        )
    ],
    indirect=True,
)
def test_create_vm_with_cloned_data_volume_grant_unprivileged_client_permissions_negative(
    namespace,
    destination_ns,
    restricted_namespace_service_account,
    unprivileged_client,
    restricted_role_binding_for_vms_in_destination_namespace,
    data_volume_clone_settings,
    permissions_src,
    permissions_destination,
):
    create_vm_negative(
        namespace=destination_ns.name,
        service_accounts=[restricted_namespace_service_account.name],
        unprivileged_client=unprivileged_client,
        data_volume_clone_settings=data_volume_clone_settings,
    )


@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, perm_src_service_account, perm_destination_service_account",
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            {PERMISSIONS_SRC_SA: DATAVOLUMES, VERBS_SRC_SA: ALL},
            {PERMISSIONS_DST_SA: DATAVOLUMES, VERBS_DST_SA: ALL},
            marks=pytest.mark.polarion("CNV-2827"),
        )
    ],
    indirect=True,
)
def test_create_vm_cloned_data_volume_restricted_ns_service_account_no_clone_perm_negative(
    namespace,
    destination_ns,
    restricted_namespace_service_account,
    unprivileged_client,
    data_volume_clone_settings,
    perm_src_service_account,
    perm_destination_service_account,
):
    create_vm_negative(
        namespace=destination_ns.name,
        service_accounts=[restricted_namespace_service_account.name],
        unprivileged_client=unprivileged_client,
        data_volume_clone_settings=data_volume_clone_settings,
    )


@pytest.mark.gating
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_module",
    [
        pytest.param(DV_PARAMS, marks=pytest.mark.polarion("CNV-2829")),
    ],
    indirect=True,
)
def test_create_vm_with_cloned_data_volume_permissions_for_pods_positive(
    unprivileged_client,
    data_volume_clone_settings,
    permission_src_service_account_for_creating_pods,
    permission_destination_service_account_for_creating_pods,
    vm_for_restricted_namespace_cloning_test,
):
    verify_snapshot_used_namespace_transfer(
        cdv=data_volume_clone_settings,
        unprivileged_client=unprivileged_client,
    )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_module, permissions_src, permissions_destination, dv_destination_cloned_from_pvc",
    [
        pytest.param(
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC: ALL},
            {PERMISSIONS_DST: DATAVOLUMES_AND_DVS_SRC, VERBS_DST: ALL},
            {"dv_name": "cnv-4034"},
            marks=pytest.mark.polarion("CNV-4034"),
        )
    ],
    indirect=True,
)
def test_disk_image_after_create_vm_with_restricted_clone(
    skip_block_volumemode_scope_module,
    dv_destination_cloned_from_pvc,
):
    create_vm_and_verify_image_permission(dv=dv_destination_cloned_from_pvc)
