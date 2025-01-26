import logging

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import get_client

from tests.storage.restricted_namespace_cloning.constants import TARGET_DV
from tests.storage.utils import assert_pvc_snapshot_clone_annotation
from utilities.constants import PVC
from utilities.storage import (
    ErrorMsg,
    create_dv,
    is_snapshot_supported_by_sc,
    sc_volume_binding_mode_is_wffc,
)

LOGGER = logging.getLogger(__name__)


def verify_snapshot_used_namespace_transfer(cdv, unprivileged_client):
    _cdv_admin = DataVolume(name=cdv.name, namespace=cdv.namespace, client=get_client())
    _cdv_admin.wait_for_dv_success()
    storage_class = cdv.storage_class
    # Namespace transfer is not possible with WFFC
    if is_snapshot_supported_by_sc(
        sc_name=storage_class, client=unprivileged_client
    ) and not sc_volume_binding_mode_is_wffc(sc=storage_class):
        assert_pvc_snapshot_clone_annotation(pvc=_cdv_admin.pvc, storage_class=storage_class)


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
