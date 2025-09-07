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


pytestmark = [pytest.mark.sno, pytest.mark.gating, pytest.mark.arm64]


@pytest.fixture()
def crds(admin_client):
    crds_to_check = []
    target_suffixes = (Resource.ApiGroup.KUBEVIRT_IO, Resource.ApiGroup.NMSTATE_IO)
    for crd in CustomResourceDefinition.get(dyn_client=admin_client):
        if crd.name in MTV_VOLUME_POPULATOR_CRDS:
            continue
        if any([
            crd.name.endswith(suffix)
            for suffix in target_suffixes
        ]):
            crds_to_check.append(crd)
    return crds_to_check


@pytest.mark.polarion("CNV-8263")
def test_crds_cluster_readers_role(crds):
    cluster_readers = "system:cluster-readers"
    unreadable_crds = []
    for crd in crds:
        can_read = check_output(shlex.split(f"oc adm policy who-can get {crd.name}"))
        if cluster_readers not in str(can_read):
            unreadable_crds.append(crd.name)

    assert not unreadable_crds, f"The following crds are missing {cluster_readers} role: {unreadable_crds}"
