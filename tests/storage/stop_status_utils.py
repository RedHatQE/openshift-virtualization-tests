from __future__ import annotations

import logging
from time import monotonic
from typing import TYPE_CHECKING

from utilities.constants.timeouts import TIMEOUT_10MIN

if TYPE_CHECKING:
    from typing import Any

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
    """Stop waiting when DataVolume phase and progress both stop changing.

    Watches ``status.phase`` and ``status.progress``. A change in either resets
    the timer. Pass a fresh ``progress_state={}`` for each DataVolume. If the
    DataVolume does not exist yet, keep waiting.

    Args:
        dv: DataVolume to check.
        progress_state: Per-DataVolume tracker. Pass ``{}``; reused across polls.
        no_progress_timeout: Seconds with no phase or progress change before stopping.

    Returns:
        True to stop waiting; False to keep waiting.

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
    phase = str(getattr(dv_status, "phase", None) or "")
    progress = str(getattr(dv_status, "progress", None) or "")
    if (phase, progress) != (progress_state.get("phase"), progress_state.get("progress")):
        LOGGER.info(f"DV {dv.name} phase={phase!r} progress={progress!r}")
        progress_state["phase"] = phase
        progress_state["progress"] = progress
        progress_state["updated_at"] = monotonic()
        return False

    no_progress_for = monotonic() - progress_state["updated_at"]
    if no_progress_for < no_progress_timeout:
        return False

    LOGGER.error(
        f"DV {dv.name} unchanged at phase={phase!r} progress={progress!r} for {no_progress_for:.0f}s; failing fast"
    )
    return True
