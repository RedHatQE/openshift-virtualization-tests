"""
Restricted namespace cloning
"""

import logging

import pytest
from ocp_resources.datavolume import DataVolume

from tests.storage.constants import ADMIN_NAMESPACE_PARAM
from tests.storage.restricted_namespace_cloning.constants import (
    ALL,
    CREATE,
    CREATE_DELETE_LIST_GET,
    DATAVOLUMES,
    DATAVOLUMES_AND_DVS_SRC,
    DATAVOLUMES_SRC,
    DV_PARAMS,
    LIST_GET,
    PERMISSIONS_DST,
    PERMISSIONS_SRC,
    VERBS_DST,
    VERBS_SRC,
)
from tests.storage.restricted_namespace_cloning.utils import create_dv_negative, verify_snapshot_used_namespace_transfer
from tests.storage.utils import verify_vm_disk_image_permission
from utilities.storage import create_vm_from_dv

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.usefixtures("skip_when_no_unprivileged_client_available")


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, permissions_datavolume_source, "
    "dv_cloned_by_unprivileged_user_in_the_same_namespace",
    [
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC: ALL},
            {"dv_name": "cnv-8905"},
            marks=pytest.mark.polarion("CNV-8905"),
        ),
    ],
    indirect=True,
)
def test_unprivileged_user_clone_dv_same_namespace_positive(
    permissions_pvc_source,
    dv_cloned_by_unprivileged_user_in_the_same_namespace,
):
    dv_cloned_by_unprivileged_user_in_the_same_namespace.wait_for_dv_success()


@pytest.mark.sno
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, "
    "permissions_datavolume_source, permissions_datavolume_destination, "
    "dv_destination_cloned_from_pvc, requested_verify_image_permissions",
    [
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC: ALL},
            {PERMISSIONS_DST: DATAVOLUMES_AND_DVS_SRC, VERBS_DST: ALL},
            {"dv_name": "cnv-2692"},
            {"verify_image_permissions": True},
            marks=pytest.mark.polarion("CNV-2692"),
            id="src_dv_and_dv_source_all_dest_dv_and_dv_source_all",
        ),
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_SRC, VERBS_SRC: CREATE},
            {PERMISSIONS_DST: DATAVOLUMES, VERBS_DST: CREATE_DELETE_LIST_GET},
            {"dv_name": "cnv-2971"},
            {"verify_image_permissions": False},
            marks=pytest.mark.polarion("CNV-2971"),
            id="src_dv_source_create_dest_dv_create_delete_list_get",
        ),
    ],
    indirect=True,
)
def test_user_permissions_positive(
    unprivileged_client,
    storage_class_matrix__module__,
    storage_class_name_scope_module,
    permissions_pvc_destination,
    dv_destination_cloned_from_pvc,
    requested_verify_image_permissions,
):
    verify_snapshot_used_namespace_transfer(cdv=dv_destination_cloned_from_pvc, unprivileged_client=unprivileged_client)
    if requested_verify_image_permissions:
        with create_vm_from_dv(dv=dv_destination_cloned_from_pvc) as vm:
            if (
                storage_class_matrix__module__[storage_class_name_scope_module]["volume_mode"]
                == DataVolume.VolumeMode.FILE
            ):
                verify_vm_disk_image_permission(vm=vm)


@pytest.mark.sno
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, "
    "permissions_datavolume_source, permissions_datavolume_destination",
    [
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES, VERBS_SRC: ALL},
            {PERMISSIONS_DST: DATAVOLUMES_AND_DVS_SRC, VERBS_DST: ALL},
            marks=pytest.mark.polarion("CNV-2793"),
            id="src_dv_all_dest_dv_and_dv_source_all",
        ),
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC: LIST_GET},
            {PERMISSIONS_DST: DATAVOLUMES_AND_DVS_SRC, VERBS_DST: ALL},
            marks=pytest.mark.polarion("CNV-2691"),
            id="src_dv_and_dv_source_list_get_dest_dv_and_dv_source_all",
        ),
    ],
    indirect=True,
)
def test_user_permissions_negative(
    storage_class_name_scope_module,
    namespace,
    data_volume_multi_storage_scope_module,
    destination_namespace,
    unprivileged_client,
    permissions_datavolume_source,
    permissions_datavolume_destination,
    user_has_get_permissions_in_source_namespace,
):
    create_dv_negative(
        namespace=destination_namespace.name,
        storage_class=storage_class_name_scope_module,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.pvc.name,
        source_namespace=data_volume_multi_storage_scope_module.namespace,
        unprivileged_client=unprivileged_client,
    )


@pytest.mark.sno
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module",
    [
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            marks=pytest.mark.polarion("CNV-2688"),
        ),
    ],
    indirect=True,
)
def test_unprivileged_user_clone_same_namespace_negative(
    storage_class_name_scope_module,
    namespace,
    data_volume_multi_storage_scope_module,
    unprivileged_client,
):
    create_dv_negative(
        namespace=namespace.name,
        storage_class=storage_class_name_scope_module,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.pvc.name,
        source_namespace=data_volume_multi_storage_scope_module.namespace,
        unprivileged_client=unprivileged_client,
    )


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, permissions_datavolume_destination",
    [
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            DV_PARAMS,
            {PERMISSIONS_DST: DATAVOLUMES_AND_DVS_SRC, VERBS_DST: ALL},
            marks=pytest.mark.polarion("CNV-8907"),
        ),
    ],
    indirect=True,
)
def test_user_permissions_only_for_dst_ns_negative(
    storage_class_name_scope_module,
    data_volume_multi_storage_scope_module,
    destination_namespace,
    unprivileged_client,
    permissions_datavolume_destination,
):
    create_dv_negative(
        namespace=destination_namespace.name,
        storage_class=storage_class_name_scope_module,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.pvc.name,
        source_namespace=data_volume_multi_storage_scope_module.namespace,
        unprivileged_client=unprivileged_client,
    )
