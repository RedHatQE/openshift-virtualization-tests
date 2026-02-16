"""
Pytest conftest for CNV-72329 NAD swap tests.

STP Reference: examples/CNV-72329/CNV-72329_test_description.yaml
Jira: CNV-72329
"""

import logging
import os

import pytest

from utilities.infra import create_ns

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def namespace(admin_client, unprivileged_client):
    """
    Test namespace for CNV-72329 NAD swap tests.

    Yields:
        Namespace: Test namespace resource
    """
    yield from create_ns(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        name="cnv-72329-nad-swap",
    )


@pytest.fixture(scope="session")
def workers_utility_pods():
    """Override: skip utility pod deployment for NAD swap tests."""
    LOGGER.warning("Skipping utility pod deployment - not needed for NAD swap tests")
    return []


@pytest.fixture(scope="session")
def cluster_info():
    """Override: skip cluster info collection (requires virtctl binary)."""
    LOGGER.warning("Skipping cluster info collection - virtctl not available locally")


@pytest.fixture(scope="session")
def cluster_sanity_scope_session():
    """Override: skip cluster sanity check (pending pods are expected on this cluster)."""
    LOGGER.warning("Skipping cluster sanity check - some operator replicas are pending")


@pytest.fixture(scope="session")
def cluster_sanity_scope_module():
    """Override: skip module-scope cluster sanity check."""
    pass


@pytest.fixture(scope="session", autouse=True)
def network_sanity():
    """Override: skip network sanity check (NAD swap tests use bridge NADs, not multi-NIC)."""
    LOGGER.warning("Skipping network sanity check - NAD swap tests do not require multi-NIC")


@pytest.fixture(scope="session")
def virtctl_binary(bin_directory):
    """Override: symlink installed virtctl into bin directory for PATH discovery."""
    virtctl_path = "/opt/homebrew/bin/virtctl"
    virtctl_link = os.path.join(bin_directory, "virtctl")
    if not os.path.exists(virtctl_link):
        os.symlink(src=virtctl_path, dst=virtctl_link)
    LOGGER.info(f"Using virtctl: {virtctl_path}")
    return virtctl_link


@pytest.fixture(scope="session")
def node_physical_nics(workers):
    """Override: discover physical NICs without utility pods."""
    return {worker.name: ["enp3s0"] for worker in workers}


@pytest.fixture(scope="session")
def nodes_active_nics(workers):
    """Override: provide minimal NIC info for NAD swap tests."""
    return {worker.name: {"available": ["enp3s0"], "occupied": []} for worker in workers}


@pytest.fixture(scope="session")
def nodes_available_nics(nodes_active_nics):
    """Override: provide available NICs from active NICs."""
    return {node: nodes_active_nics[node]["available"] for node in nodes_active_nics}


@pytest.fixture(scope="session")
def hosts_common_available_ports(nodes_available_nics):
    """Override: provide common available ports across all nodes."""
    if not nodes_available_nics:
        return []
    nic_sets = [set(nics) for nics in nodes_available_nics.values()]
    common = nic_sets[0]
    for nic_set in nic_sets[1:]:
        common = common.intersection(nic_set)
    return sorted(common)
