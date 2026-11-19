"""Selection of the node audit log files that hold the events of a test session.

Scope: naming, timestamp parsing and session-window filtering of the OpenShift
node audit logs reported by ``oc adm logs``.

Does not belong here:
- reading audit log content or extracting matching entries -> ``utilities/infra.py``
  (``get_node_audit_log_entries``, ``get_node_audit_log_line_dict``)
- running ``oc`` commands -> ``utilities/infra.py``
"""

import logging
import re
from bisect import bisect_left
from datetime import datetime

LOGGER = logging.getLogger(__name__)

AUDIT_LOG_NAME_PATTERN = re.compile(r"audit-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2}\.\d{3})\.log")
ACTIVE_AUDIT_LOG_NAME = "audit.log"


def _rotated_audit_log_timestamp(*, log_name: str) -> datetime | None:
    """Extract the timestamp embedded in a rotated audit log file name.

    Args:
        log_name: Audit log file name, as reported by ``oc adm logs``.

    Returns:
        The timestamp of the rotated log, or None when the name is not a rotated audit log
        or carries a timestamp that does not parse.
    """
    match = AUDIT_LOG_NAME_PATTERN.match(string=log_name)
    if not match:
        LOGGER.info(f"Skipping non-audit file: {log_name}")
        return None

    timestamp_str = f"{match.group(1)}T{match.group(2)}:{match.group(3)}:{match.group(4)}"
    try:
        return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError as err:
        LOGGER.warning(f"Invalid timestamp in log {log_name}: {err}")
        return None


def audit_log_files_per_node(*, command_output: list[str]) -> dict[str, list[str | tuple[str, datetime]]]:
    """Group audit log file names by the node that holds them.

    Args:
        command_output: Lines reported by ``oc adm logs``, each formatted as ``<node> <log-name>``.

    Returns:
        Node name to its audit log entries, where the active log is a plain name and each
        rotated log is a ``(name, timestamp)`` tuple.
    """
    audit_log_files: dict[str, list[str | tuple[str, datetime]]] = {}
    for line in command_output:
        parts = line.split()
        if len(parts) != 2:
            LOGGER.error(f"Fail to get log: {line}")
            continue

        node, log_name = parts
        if log_name == ACTIVE_AUDIT_LOG_NAME:
            audit_log_files.setdefault(node, []).append(log_name)
            continue

        log_timestamp = _rotated_audit_log_timestamp(log_name=log_name)
        if log_timestamp:
            audit_log_files.setdefault(node, []).append((log_name, log_timestamp))

    return audit_log_files


def relevant_audit_logs(*, log_entries: list[str | tuple[str, datetime]], session_start_time: datetime) -> list[str]:
    """Select the audit logs that can hold events of the current session.

    The active log is always kept, together with every rotated log from the one immediately
    preceding ``session_start_time`` to the newest one, so events written just before the
    session start are not missed.

    Args:
        log_entries: Audit log entries of a single node, as returned by ``audit_log_files_per_node``.
        session_start_time: Start time of the current test session.

    Returns:
        The relevant rotated log names followed by the active log names.
    """
    active_logs = [log_name for log_name in log_entries if isinstance(log_name, str)]
    rotated_with_timestamps = sorted(
        (entry for entry in log_entries if isinstance(entry, tuple)), key=lambda entry: entry[1]
    )
    timestamps = [timestamp for _, timestamp in rotated_with_timestamps]
    start_index = max(0, bisect_left(a=timestamps, x=session_start_time) - 1)
    relevant_rotated = [log_name for log_name, _ in rotated_with_timestamps[start_index:]]

    return relevant_rotated + active_logs
