"""Cluster infrastructure topology and platform fixtures."""

import logging

import pytest
from ocp_resources.infrastructure import Infrastructure
from pytest_testconfig import config as py_config

from libs.net.cluster import ipv4_supported_cluster, ipv6_supported_cluster
from utilities.constants.architecture import S390X
from utilities.constants.cluster import NODE_TYPE_WORKER_LABEL
from utilities.infra import get_cluster_platform, get_infrastructure, label_nodes, run_virtctl_command
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
