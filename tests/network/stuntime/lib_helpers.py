import itertools
import logging
import re

LOGGER = logging.getLogger(__name__)


class InsufficientStuntimeDataError(ValueError):
    """Raised when ping log has too few replies to compute stuntime."""


def compute_stuntime(ping_log: str) -> float:
    """Parse ping -D output and compute stuntime as the largest gap between successful replies.

    Stuntime is the connectivity gap duration: the largest interval where no ICMP replies
    were received. For example, with ping at 0.1s intervals, any gap > 0.1s indicates packet loss.

    Args:
        ping_log: Raw output from ping -D (timestamped lines).

    Returns:
        Stuntime in seconds (float).

    Raises:
        InsufficientStuntimeDataError: When ping log has fewer than 2 reply timestamps.
    """
    timestamps: list[float] = []
    for line in ping_log.splitlines():
        if "bytes from" in line or "icmp_seq=" in line:
            match = re.search(r"\[(\d+\.\d+)\]", line)
            if match:
                timestamps.append(float(match.group(1)))

    if len(timestamps) < 2:
        raise InsufficientStuntimeDataError(
            f"Insufficient data to compute stuntime: {len(timestamps)} reply timestamps (need at least 2)"
        )

    stuntime = max(b - a for a, b in itertools.pairwise(timestamps))
    session_duration = timestamps[-1] - timestamps[0]
    LOGGER.info(f"Total ping session={session_duration:.3f}s, stuntime={stuntime:.3f}s")
    return stuntime
