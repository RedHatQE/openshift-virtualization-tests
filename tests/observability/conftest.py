import logging
import re

import pytest
from ocp_resources.ssp import SSP
from packaging.version import Version

from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.jira import is_jira_open

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def paused_ssp_operator(admin_client, hco_namespace, ssp_resource_scope_class):
    """
    Pause ssp-operator to avoid from reconciling any related objects
    """
    with ResourceEditorValidateHCOReconcile(
        patches={ssp_resource_scope_class: {"metadata": {"annotations": {"kubevirt.io/operator.paused": "true"}}}},
        list_resource_reconcile=[SSP],
    ):
        yield


@pytest.fixture(scope="session")
def workers_rhcos_version(schedulable_nodes):
    """Returns a dict mapping each schedulable node name to its RHCOS version.

    Returns:
        dict[str, str]: Node name to RHCOS version (e.g. {"node-1": "10.2.20260408", ...}).
    """
    rhcos_version_re = re.compile(r"CoreOS\s+([\d.]+)")
    versions = {}
    for node in schedulable_nodes:
        os_image = node.instance.status.nodeInfo.osImage
        match = rhcos_version_re.search(string=os_image)
        assert match, f"Failed to parse RHCOS version from osImage '{os_image}' on node '{node.name}'"
        versions[node.name] = match.group(1)
    return versions


@pytest.fixture(scope="session")
def cluster_has_rhcos10_or_above(workers_rhcos_version):
    return any(Version(ver) >= Version("10") for ver in workers_rhcos_version.values())


@pytest.fixture(scope="session")
def skip_when_hco_metrics_scraping_bug_open(cluster_has_rhcos10_or_above):
    if cluster_has_rhcos10_or_above and is_jira_open(jira_id="CNV-87184"):
        pytest.xfail(reason="CNV-87184: HCO metrics scraping fails with 401 Unauthorized on RHCOS 10+")


@pytest.fixture(scope="session")
def is_postcopy_migration_bug_open(cluster_has_rhcos10_or_above):
    return cluster_has_rhcos10_or_above and is_jira_open(jira_id="CNV-84023")
