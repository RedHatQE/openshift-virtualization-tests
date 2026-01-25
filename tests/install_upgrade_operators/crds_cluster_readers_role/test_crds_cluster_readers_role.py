import logging
import shlex
from subprocess import check_output

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.resource import Resource
from timeout_sampler import retry

from utilities.constants import BASE_EXCEPTIONS_DICT, TIMEOUT_3MIN, TIMEOUT_10SEC
from utilities.jira import is_jira_open

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.sno,
    pytest.mark.gating,
    pytest.mark.arm64,
    pytest.mark.s390x,
    pytest.mark.conformance,
    pytest.mark.skip_must_gather_collection,
]

UNREADABLE_CRDS_BY_JIRA = {
    "CNV-76680": [
        f"multinamespacevirtualmachinestoragemigrationplans.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
        f"multinamespacevirtualmachinestoragemigrations.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
        f"virtualmachinestoragemigrationplans.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
        f"virtualmachinestoragemigrations.{Resource.ApiGroup.MIGRATIONS_KUBEVIRT_IO}",
    ],
    "CNV-76369": [
        f"virtualmachinebackuptrackers.backup.{Resource.ApiGroup.KUBEVIRT_IO}",
    ],
}


@retry(
    wait_timeout=TIMEOUT_3MIN,
    sleep=TIMEOUT_10SEC,
    exceptions_dict=BASE_EXCEPTIONS_DICT,
)
def get_cnv_crds(admin_client: DynamicClient) -> list[CustomResourceDefinition]:
    """
    Fetch CNV-related CRDs with retry logic to handle large responses and network instability.

    Large CRD listings (10MB+) can trigger ProtocolError/IncompleteRead under unstable
    network conditions. Retries mitigate transient failures; repeated failures may indicate
    cluster or network issues.
    """
    return [
        crd
        for crd in CustomResourceDefinition.get(client=admin_client)
        if crd.name.endswith(Resource.ApiGroup.KUBEVIRT_IO)
    ]


@pytest.fixture()
def crds_with_open_jira():
    """
    Map CRD names to open Jira IDs.

    Returns:
        dict[str, str]: Mapping of CRD name to open Jira ID.
    """
    return {
        crd_name: jira_id
        for jira_id, crd_list in UNREADABLE_CRDS_BY_JIRA.items()
        if is_jira_open(jira_id=jira_id)
        for crd_name in crd_list
    }


@pytest.mark.polarion("CNV-8263")
def test_crds_cluster_readers_role(admin_client, crds_with_open_jira):
    cluster_readers = "system:cluster-readers"
    unreadable_crds = []
    for crd in get_cnv_crds(admin_client=admin_client):
        if crd.name in crds_with_open_jira:
            LOGGER.warning(
                f"Skipping {crd.name} because it is unreadable due to a product bug.",
                extra={"crd_name": crd.name, "jira_id": crds_with_open_jira[crd.name]},
            )
            continue
        can_read = check_output(shlex.split(f"oc adm policy who-can get {crd.name}"))
        if cluster_readers not in str(can_read):
            unreadable_crds.append(crd.name)

    assert not unreadable_crds, f"The following crds are missing {cluster_readers} role: {unreadable_crds}"
