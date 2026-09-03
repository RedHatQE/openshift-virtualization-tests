"""Cluster infrastructure topology and platform fixtures."""

import logging
import re
import subprocess
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime

import pytest
from ocp_resources.infrastructure import Infrastructure
from ocp_resources.pod import Pod
from pytest_testconfig import config as py_config

from libs.net.cluster import ipv4_supported_cluster, ipv6_supported_cluster
from utilities.constants.architecture import S390X
from utilities.constants.cluster import AUDIT_LOGS_PATH, NODE_TYPE_WORKER_LABEL, OC_ADM_LOGS_COMMAND
from utilities.infra import (
    get_cluster_platform,
    get_infrastructure,
    label_nodes,
    run_virtctl_command,
)
from utilities.network import get_cluster_cni_type
from utilities.operator import get_machine_config_pool_by_name

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def cluster_info(
    admin_client,
    installing_cnv,
    openshift_current_version,
    cnv_current_version,
    hco_image,
    ocs_current_version,
    kubevirt_resource_scope_session,
    workers_type,
):
    title = "\nCluster info:\n"
    virtctl_client_version, virtctl_server_version = None, None
    if not installing_cnv:
        virtctl_client_version, virtctl_server_version = (
            run_virtctl_command(command=["version"])[1].strip().splitlines()
        )

    LOGGER.info(
        f"{title}"
        f"\tOpenshift version: {openshift_current_version}\n"
        f"\tCNV version: {cnv_current_version}\n"
        f"\tHCO image: {hco_image}\n"
        f"\tOCS version: {ocs_current_version}\n"
        f"\tCNI type: {get_cluster_cni_type(admin_client=admin_client)}\n"
        f"\tWorkers type: {workers_type}\n"
        f"\tCluster CPU Architecture: {', '.join(py_config['cluster_arch'])}\n"
        f"\tIPv4 cluster: {ipv4_supported_cluster()}\n"
        f"\tIPv6 cluster: {ipv6_supported_cluster()}\n"
        f"\tVirtctl version: \n\t{virtctl_client_version}\n\t{virtctl_server_version}\n"
    )


@pytest.fixture(scope="session")
def sno_cluster(admin_client):
    return get_infrastructure(admin_client=admin_client).instance.status.infrastructureTopology == "SingleReplica"


@pytest.fixture(scope="session")
def compact_cluster(nodes, workers, control_plane_nodes):
    return len(nodes) == len(workers) == len(control_plane_nodes) == 3


@pytest.fixture(scope="session")
def is_aws_cluster(admin_client):
    return get_cluster_platform(admin_client=admin_client) == Infrastructure.Type.AWS


@pytest.fixture(scope="session")
def skip_on_aws_cluster(is_aws_cluster):
    if is_aws_cluster:
        pytest.skip("This test is skipped on an AWS cluster")


@pytest.fixture(scope="session")
def fips_enabled_cluster(workers_utility_pods):
    """Check if FIPS is enabled on cluster"""
    for pod in workers_utility_pods:
        # command output: 0 == fips disabled
        #                 1 == fips enabled
        cluster_fips_status = pod.execute(["bash", "-c", "cat /proc/sys/crypto/fips_enabled"]).strip()
        if int(cluster_fips_status) == 1:
            return True
    return False


@pytest.fixture(scope="session")
def is_s390x_cluster(nodes_cpu_architecture):
    return nodes_cpu_architecture == S390X


@pytest.fixture(scope="session")
def is_disconnected_cluster():
    # To enable disconnected_cluster pass --tc=disconnected_cluster:True to pytest commandline.
    return py_config.get("disconnected_cluster")


@pytest.fixture(scope="session")
def label_schedulable_nodes(schedulable_nodes):
    yield from label_nodes(nodes=schedulable_nodes, labels=NODE_TYPE_WORKER_LABEL)


@pytest.fixture(scope="session")
def machine_config_pools(admin_client):
    return [
        get_machine_config_pool_by_name(mcp_name="master", admin_client=admin_client),
        get_machine_config_pool_by_name(mcp_name="worker", admin_client=admin_client),
    ]


@pytest.fixture(scope="module")
def cnv_pods(admin_client, hco_namespace):
    yield list(Pod.get(client=admin_client, namespace=hco_namespace.name))


@pytest.fixture()
def audit_logs(session_start_time):
    """
    Get audit logs names filtered by session start time.

    Only returns audit logs that are relevant to the current test session:
    - The active audit.log file
    - Rotated files with timestamps >= session_start_time
    - The immediately previous rotated file (to catch events just before session start)
    """
    audit_log_pattern = re.compile(r"audit-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2}\.\d{3})\.log")
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
        match = audit_log_pattern.match(string=log)
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
