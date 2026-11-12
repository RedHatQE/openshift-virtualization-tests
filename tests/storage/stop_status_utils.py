from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from utilities.constants.timeouts import TIMEOUT_10MIN

if TYPE_CHECKING:
    from ocp_resources.datavolume import DataVolume

LOGGER = logging.getLogger(__name__)


def dv_stop_status_restart_threshold(dv: DataVolume, restart_count_threshold: int = 3) -> bool:
    """Function for detecting excessive DV restarts.

    Args:
        dv: The DataVolume to check.
        restart_count_threshold: The threshold for restart count (default: 3).

    Returns:
        True if restarts exceed threshold.

    Example::
        dv.wait_for_dv_success(
            stop_status_func=dv_stop_status_restart_threshold,
            dv=dv,
            restart_count_threshold=4,
        )
    """
    dv_status = getattr(dv.instance, "status", None)
    restart_count = getattr(dv_status, "restartCount", 0) or 0
    if restart_count >= restart_count_threshold:
        LOGGER.error(f"DV {dv.name} has {restart_count} restarts, stopping")
        return True
    return False


def dv_stop_status_no_progress(
    dv: DataVolume,
    progress_state: dict[str, Any],
    no_progress_timeout: int = TIMEOUT_10MIN,
) -> bool:
    """Abort wait_for_dv_success when status.progress stops changing.

    Returns False while the DataVolume is absent so polling can continue.

    Example::
        dv.wait_for_dv_success(
            stop_status_func=dv_stop_status_no_progress,
            dv=dv,
            progress_state={},
        )
    """
    dv_instance = dv.exists
    if dv_instance is None:
        return False

    dv_status = getattr(dv_instance, "status", None)
    progress = str(getattr(dv_status, "progress", None) or "")
    if progress != progress_state.get("progress"):
        LOGGER.info(f"DV {dv.name} import progress: {progress!r}")
        progress_state["progress"] = progress
        progress_state["updated_at"] = time.monotonic()
        return False

    no_progress_for = time.monotonic() - progress_state["updated_at"]
    if no_progress_for < no_progress_timeout:
        return False

    LOGGER.error(f"DV {dv.name} import has no progress at {progress!r} for {no_progress_for:.0f}s; failing fast")
    return True
