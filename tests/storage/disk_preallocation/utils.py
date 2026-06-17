from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ocp_resources.resource import NamespacedResource
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_2MIN

if TYPE_CHECKING:
    from ocp_resources.cdi_config import CDIConfig
    from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

LOGGER = logging.getLogger(__name__)


def assert_preallocation_requested_annotation(pvc: PersistentVolumeClaim, status: str) -> None:
    preallocation_requested_annotation = (
        f"{NamespacedResource.ApiGroup.CDI_KUBEVIRT_IO}/storage.preallocation.requested"
    )
    assert pvc.instance.metadata.annotations.get(preallocation_requested_annotation) == status, (
        f"'{preallocation_requested_annotation}' should be '{status}'"
    )


def assert_preallocation_annotation(pvc: PersistentVolumeClaim, res: str) -> None:
    preallocation_annotation = f"{NamespacedResource.ApiGroup.CDI_KUBEVIRT_IO}/storage.preallocation"
    assert pvc.instance.metadata.annotations.get(preallocation_annotation) == res, (
        f"'{preallocation_annotation}' should be '{res}'"
    )


def wait_for_cdi_preallocation_enabled(cdi_config: CDIConfig, expected_value: bool) -> None:
    preallocation_status = ""
    try:
        for preallocation_status in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=1,
            func=lambda: cdi_config.instance.status.preallocation,
        ):
            if preallocation_status == expected_value:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"CDIconfig status.preallocation is '{preallocation_status}', but expected to be '{expected_value}'"
        )
        raise
