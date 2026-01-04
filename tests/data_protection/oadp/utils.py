import logging

from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.storage_profile import StorageProfile

from utilities.constants import (
    TIMEOUT_10SEC,
    TIMEOUT_15SEC,
)

LOGGER = logging.getLogger(__name__)


def is_storage_class_support_volume_mode(storage_class_name, requested_volume_mode):
    for claim_property_set in StorageProfile(name=storage_class_name).claim_property_sets:
        if claim_property_set.volumeMode == requested_volume_mode:
            return True
    return False


def wait_for_restored_dv(dv):
    dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_15SEC)
    dv.wait_for_dv_success(timeout=TIMEOUT_10SEC)
