from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ocp_resources.datavolume import DataVolume

LOGGER = logging.getLogger(__name__)


def dv_stop_status_restart_threshold(dv: DataVolume, restart_count_threshold: int = 3) -> bool:
    """Returns a stop status function that detects excessive DV restarts.

    The returned closure accepts a DataVolume and returns True if the restart
    count exceeds the threshold (default: 3).

    Returns:
        True if restarts exceed threshold.

    Example::
        dv.wait_for_dv_success(
            stop_status_func=dv_stop_status_after_three_restarts,
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
