from __future__ import annotations

import logging
from time import monotonic
from typing import TYPE_CHECKING

from ocp_resources.datavolume import DataVolume

from utilities.constants.timeouts import TIMEOUT_10MIN, TIMEOUT_30MIN

if TYPE_CHECKING:
    from typing import Any

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

    Args:
        dv: DataVolume to check.
        progress_state: Per-DataVolume tracker. Must start as ``{}``; the function
            writes ``last_seen`` and ``updated_at`` into it. An absent or deleted
            DataVolume keeps waiting; if the timer was already armed it is still
            enforced. Timer arms only after a real progress percentage is seen
            (not ``None`` / ``""`` / ``N/A``).
        no_progress_timeout: Seconds with no phase/progress change before stopping.

    Returns:
        True to stop waiting; False to keep waiting.
    """
    dv_instance = dv.exists
    if dv_instance is not None:
        phase_and_progress = (
            dv_instance.get("status", {}).get("phase"),
            dv_instance.get("status", {}).get("progress"),
        )
        if phase_and_progress[1] in (None, "", "N/A"):
            return False
        if phase_and_progress != progress_state.get("last_seen"):
            LOGGER.info(f"DV {dv.name} phase/progress={phase_and_progress}")
            progress_state.update(last_seen=phase_and_progress, updated_at=monotonic())
            return False

    # Missing DV (dshchedr) or unchanged phase/progress: same no_progress check.
    updated_at = progress_state.get("updated_at")
    if updated_at is None:
        return False
    no_progress_for = monotonic() - updated_at
    if no_progress_for < no_progress_timeout:
        return False

    LOGGER.error(
        f"DV {dv.name} unchanged at phase/progress={progress_state.get('last_seen')} "
        f"for {no_progress_for:.0f}s; failing fast"
    )
    return True


def wait_for_vm_data_volumes_no_progress(vm, timeout: int = TIMEOUT_30MIN) -> None:
    """Wait for every DataVolume of vm to succeed, failing fast when import stops progressing."""
    for volume in vm.instance.spec.template.spec.volumes:
        if "dataVolume" not in volume.keys():
            continue
        dv = DataVolume(name=volume.dataVolume.name, namespace=vm.namespace, client=vm.client)
        dv.wait_for_dv_success(
            timeout=timeout,
            stop_status_func=dv_stop_status_no_progress,
            dv=dv,
            progress_state={},
        )
