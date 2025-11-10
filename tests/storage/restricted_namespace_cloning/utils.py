import contextlib
import logging
from http.client import RemoteDisconnected

import pytest
import urllib3
from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from timeout_sampler import TimeoutSampler

from tests.storage.restricted_namespace_cloning.constants import TARGET_DV
from tests.storage.utils import assert_pvc_snapshot_clone_annotation
from utilities.constants import PVC, TIMEOUT_2MIN
from utilities.storage import (
    ErrorMsg,
    create_dv,
    is_snapshot_supported_by_sc,
    sc_volume_binding_mode_is_wffc,
)

LOGGER = logging.getLogger(__name__)


def verify_snapshot_used_namespace_transfer(cdv: DataVolume, unprivileged_client: DynamicClient) -> None:
    storage_class = cdv.storage_class
    # Namespace transfer is not possible with WFFC
    if is_snapshot_supported_by_sc(
        sc_name=storage_class, client=unprivileged_client
    ) and not sc_volume_binding_mode_is_wffc(sc=storage_class):
        assert_pvc_snapshot_clone_annotation(pvc=cdv.pvc, storage_class=storage_class)


def create_dv_negative(
    namespace: str,
    storage_class: str,
    size: str,
    source_pvc: str,
    source_namespace: str,
    unprivileged_client: DynamicClient,
) -> None:
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
            storage_class=storage_class,
        ):
            LOGGER.error("Target dv was created, but shouldn't have been")


@contextlib.contextmanager
def create_dv_with_retry(**kwargs):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=5,
        func=lambda: None,
        exceptions_dict={urllib3.exceptions.ProtocolError: [], RemoteDisconnected: []},
    )
    last_exception = None
    for _ in sampler:
        try:
            with create_dv(**kwargs) as dv:
                yield dv
                return  # success - exit after yield
        except (urllib3.exceptions.ProtocolError, RemoteDisconnected) as e:
            last_exception = e
            LOGGER.warning(f"DV creation failed with {type(e).__name__}, retrying...")

    if last_exception:
        LOGGER.error(f"DV creation failed after {TIMEOUT_2MIN}: {last_exception}")
        raise last_exception
    raise RuntimeError("DV creation failed - unknown reason")
