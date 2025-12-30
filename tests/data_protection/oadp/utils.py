import logging

from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

from utilities.constants import (
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
)

LOGGER = logging.getLogger(__name__)


def wait_for_restored_dv(dv):
    dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_15SEC)
    dv.wait_for_dv_success(timeout=TIMEOUT_10SEC)
