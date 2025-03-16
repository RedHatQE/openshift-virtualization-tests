import logging
import shlex
from subprocess import check_output

import pytest
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.resource import Resource

from utilities.infra import is_jira_open

LOGGER = logging.getLogger(__name__)
MTV_VOLUME_POPULATOR_CRDS = [
    f"openstackvolumepopulators.forklift.cdi.{Resource.ApiGroup.KUBEVIRT_IO}",
    f"ovirtvolumepopulators.forklift.cdi.{Resource.ApiGroup.KUBEVIRT_IO}",
]


pytestmark = [pytest.mark.sno, pytest.mark.gating]


@pytest.fixture()
def crds(admin_client):
    crds_to_check = []
    bug_status = is_jira_open(jira_id="CNV-58119")
    for crd in CustomResourceDefinition.get(dyn_client=admin_client):
        if bug_status and crd.name in MTV_VOLUME_POPULATOR_CRDS:
            continue
        if any([
            crd.name.endswith(suffix)
            for suffix in [
                Resource.ApiGroup.KUBEVIRT_IO,
                Resource.ApiGroup.NMSTATE_IO,
            ]
        ]):
            crds_to_check.append(crd)
    return crds_to_check


@pytest.mark.polarion("CNV-8263")
def test_crds_cluster_readers_role(crds):
    LOGGER.info(f"CRds: {crds}")
    cluster_readers = "system:cluster-readers"
    cannot_read = []
    for crd in crds:
        can_read = check_output(shlex.split(f"oc adm policy who-can get {crd.name}"))
        if cluster_readers not in str(can_read):
            cannot_read.append(crd.name)

    if cannot_read:
        cannot_read_str = "\n".join(cannot_read)
        pytest.fail(reason=f"The following crds are missing {cluster_readers} role:\n{cannot_read_str}")
