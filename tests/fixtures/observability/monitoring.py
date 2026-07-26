import logging
import re
import subprocess
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime

import pytest
from ocp_utilities.monitoring import Prometheus

from utilities.constants.cluster import AUDIT_LOGS_PATH, OC_ADM_LOGS_COMMAND
from utilities.infra import get_prometheus_k8s_token

LOGGER = logging.getLogger(__name__)

AUDIT_LOG_PATTERN = re.compile(r"audit-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2}\.\d{3})\.log")


@pytest.fixture(scope="session")
def prometheus():
    return Prometheus(
        verify_ssl=False,
        bearer_token=get_prometheus_k8s_token(duration="86400s"),
    )


@pytest.fixture()
def audit_logs(session_start_time):
    """
    Get audit logs names filtered by session start time.

    Only returns audit logs that are relevant to the current test session:
    - The active audit.log file
    - Rotated files with timestamps >= session_start_time
    - The immediately previous rotated file (to catch events just before session start)
    """
    output = subprocess.getoutput(
        f"{OC_ADM_LOGS_COMMAND} --role=control-plane {AUDIT_LOGS_PATH} | grep audit"
    ).splitlines()

    nodes_logs = defaultdict(list)
    for line in output:
        parts = line.split()
        if len(parts) != 2:
            LOGGER.error(f"Fail to get log: {line}")
            continue

        node, log = parts

        # Always include active audit.log
        if log == "audit.log":
            nodes_logs[node].append(log)
            continue

        # Parse timestamp from rotated file name using regex
        match = AUDIT_LOG_PATTERN.match(string=log)
        if match:
            # Rebuild ISO format: YYYY-MM-DDTHH:MM:SS.mmm
            timestamp_str = f"{match.group(1)}T{match.group(2)}:{match.group(3)}:{match.group(4)}"
            try:
                log_timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%f")
                nodes_logs[node].append((log, log_timestamp))
            except ValueError as err:
                LOGGER.warning(f"Invalid timestamp in log {log}: {err}")
        else:
            LOGGER.info(f"Skipping non-audit file: {log}")

    # Filter rotated logs to keep only relevant ones
    filtered_nodes_logs = {}
    for node, logs in nodes_logs.items():
        # Separate active audit.log from rotated files with timestamps
        active_logs = [log for log in logs if isinstance(log, str)]
        rotated_with_ts = sorted([item for item in logs if isinstance(item, tuple)], key=lambda x: x[1])

        # Find where session_start_time fits in the sorted rotated logs using binary search
        timestamps = [ts for _, ts in rotated_with_ts]
        idx = bisect_left(a=timestamps, x=session_start_time)

        # Slice: Start one index back (if exists) to get the "immediately previous" log
        start_idx = max(0, idx - 1)
        relevant_rotated = [log for log, ts in rotated_with_ts[start_idx:]]

        final_logs = relevant_rotated + active_logs

        if final_logs:
            filtered_nodes_logs[node] = final_logs
            LOGGER.info(f"Node {node}: processing {len(final_logs)} audit log(s) (filtered from {len(logs)} total)")

    return filtered_nodes_logs
