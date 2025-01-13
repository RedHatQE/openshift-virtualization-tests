"""
Restricted namespace cloning
"""

import logging

import pytest
from kubernetes.client.rest import ApiException

from tests.storage.constants import NAMESPACE_PARAMS
from tests.storage.restricted_namespace_cloning.constants import (
    ALL,
    CREATE,
    CREATE_DELETE,
    CREATE_DELETE_LIST_GET,
    DATAVOLUMES,
    DATAVOLUMES_AND_DVS_SRC,
    DATAVOLUMES_SRC,
    DV_PARAMS,
    LIST_GET,
    PERMISSIONS_DST,
    PERMISSIONS_SRC,
    TARGET_DV,
    VERBS_DST,
    VERBS_SRC,
)
from tests.storage.utils import (
    create_vm_from_dv,
    verify_snapshot_used_namespace_transfer,
)
from utilities.constants import PVC
from utilities.storage import ErrorMsg, create_dv

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.usefixtures("skip_when_no_unprivileged_client_available")


def create_dv_negative(
    namespace,
    storage_class_dict,
    size,
    source_pvc,
    source_namespace,
    unprivileged_client,
):
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with create_dv(
            dv_name=TARGET_DV,
            namespace=namespace,
            source=PVC,
            size=size,
            source_pvc=source_pvc,
            source_namespace=source_namespace,
            client=unprivileged_client,
            storage_class=[*storage_class_dict][0],
        ):
            LOGGER.error("Target dv was created, but shouldn't have been")


@pytest.mark.sno
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module",
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            marks=pytest.mark.polarion("CNV-2688"),
        ),
    ],
    indirect=True,
)
def test_unprivileged_user_clone_same_namespace_negative(
    storage_class_matrix__module__,
    namespace,
    data_volume_multi_storage_scope_module,
    unprivileged_client,
):
    create_dv_negative(
        namespace=namespace.name,
        storage_class_dict=storage_class_matrix__module__,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.pvc.name,
        source_namespace=data_volume_multi_storage_scope_module.namespace,
        unprivileged_client=unprivileged_client,
    )


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_module, permissions_src, dv_cloned_by_unprivileged_user_in_the_same_namespace",
    [
        pytest.param(
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC: ALL},
            {"dv_name": "cnv-8905"},
            marks=pytest.mark.polarion("CNV-8905"),
        ),
    ],
    indirect=True,
)
def test_unprivileged_user_clone_same_namespace_positive(
    dv_cloned_by_unprivileged_user_in_the_same_namespace,
):
    with create_vm_from_dv(dv=dv_cloned_by_unprivileged_user_in_the_same_namespace):
        return


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module",
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            marks=pytest.mark.polarion("CNV-8906"),
        ),
    ],
    indirect=True,
)
def test_unprivileged_user_clone_different_namespaces_negative(
    storage_class_matrix__module__,
    data_volume_multi_storage_scope_module,
    unprivileged_client,
    destination_ns,
):
    create_dv_negative(
        namespace=destination_ns.name,
        storage_class_dict=storage_class_matrix__module__,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.pvc.name,
        source_namespace=data_volume_multi_storage_scope_module.namespace,
        unprivileged_client=unprivileged_client,
    )


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_module, permissions_src, permissions_destination, dv_destination_cloned_from_pvc",
    [
        pytest.param(
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC: CREATE_DELETE},
            {
                PERMISSIONS_DST: DATAVOLUMES_AND_DVS_SRC,
                VERBS_DST: CREATE_DELETE_LIST_GET,
            },
            {"dv_name": "cnv-2689"},
            marks=pytest.mark.polarion("CNV-2689"),
            id="src_ns: dv and dv/src, verbs: create, delete. dst: dv and dv/src, verbs: create, delete, list, get.",
        ),
        pytest.param(
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC: ALL},
            {PERMISSIONS_DST: DATAVOLUMES_AND_DVS_SRC, VERBS_DST: ALL},
            {"dv_name": "cnv-2692"},
            marks=pytest.mark.polarion("CNV-2692"),
            id="src_ns: dv and dv/src, verbs: *. dst: dv and dv/src, verbs: *.",
        ),
        pytest.param(
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC: ALL},
            {PERMISSIONS_DST: DATAVOLUMES, VERBS_DST: ALL},
            {"dv_name": "cnv-2805"},
            marks=pytest.mark.polarion("CNV-2805"),
            id="src_ns: dv and dv/src, verbs: *. dst: dv, verbs: *.",
        ),
        pytest.param(
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_AND_DVS_SRC, VERBS_SRC: CREATE_DELETE},
            {PERMISSIONS_DST: DATAVOLUMES, VERBS_DST: CREATE_DELETE_LIST_GET},
            {"dv_name": "cnv-2808"},
            marks=pytest.mark.polarion("CNV-2808"),
            id="src_ns: dv and dv/src, verbs: create, delete. dst: dv, verbs: create, delete, list, get.",
        ),
        pytest.param(
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES_SRC, VERBS_SRC: CREATE},
            {PERMISSIONS_DST: DATAVOLUMES, VERBS_DST: CREATE_DELETE_LIST_GET},
            {"dv_name": "cnv-2971"},
            marks=pytest.mark.polarion("CNV-2971"),
            id="src_ns: dv/src, verbs: create. dst: dv, verbs: create, delete, list, get.",
        ),
    ],
    indirect=True,
)
def test_user_permissions_positive(dv_destination_cloned_from_pvc, unprivileged_client):
    verify_snapshot_used_namespace_transfer(cdv=dv_destination_cloned_from_pvc, unprivileged_client=unprivileged_client)
    with create_vm_from_dv(dv=dv_destination_cloned_from_pvc):
        return


@pytest.mark.sno
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, permissions_src, permissions_destination",
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES, VERBS_SRC: CREATE_DELETE},
            {PERMISSIONS_DST: DATAVOLUMES, VERBS_DST: CREATE_DELETE},
            marks=pytest.mark.polarion("CNV-2793"),
            id="src_ns: dv, verbs: create, delete. dst: dv, verbs: create, delete.",
        ),
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES, VERBS_SRC: LIST_GET},
            {PERMISSIONS_DST: DATAVOLUMES_AND_DVS_SRC, VERBS_DST: ALL},
            marks=pytest.mark.polarion("CNV-2691"),
            id="src_ns: dv, verbs: list, get. dst: dv and dv/src, verbs: *.",
        ),
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            {PERMISSIONS_SRC: DATAVOLUMES, VERBS_SRC: ALL},
            {PERMISSIONS_DST: DATAVOLUMES, VERBS_DST: ALL},
            marks=pytest.mark.polarion("CNV-2804"),
            id="src_ns: dv, verbs: *. dst: dv, verbs: *.",
        ),
    ],
    indirect=True,
)
def test_user_permissions_negative(
    storage_class_matrix__module__,
    namespace,
    data_volume_multi_storage_scope_module,
    destination_ns,
    unprivileged_client,
    permissions_src,
    permissions_destination,
):
    create_dv_negative(
        namespace=destination_ns.name,
        storage_class_dict=storage_class_matrix__module__,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.pvc.name,
        source_namespace=data_volume_multi_storage_scope_module.namespace,
        unprivileged_client=unprivileged_client,
    )


@pytest.mark.sno
@pytest.mark.parametrize(
    "namespace, data_volume_multi_storage_scope_module, permissions_destination",
    [
        pytest.param(
            NAMESPACE_PARAMS,
            DV_PARAMS,
            {PERMISSIONS_DST: DATAVOLUMES_AND_DVS_SRC, VERBS_DST: ALL},
            marks=pytest.mark.polarion("CNV-8907"),
        ),
    ],
    indirect=True,
)
def test_user_permissions_only_for_dst_ns_negative(
    storage_class_matrix__module__,
    data_volume_multi_storage_scope_module,
    destination_ns,
    unprivileged_client,
    permissions_destination,
):
    create_dv_negative(
        namespace=destination_ns.name,
        storage_class_dict=storage_class_matrix__module__,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.pvc.name,
        source_namespace=data_volume_multi_storage_scope_module.namespace,
        unprivileged_client=unprivileged_client,
    )
