import logging
import shlex
from subprocess import check_output

import pytest
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.resource import Resource

LOGGER = logging.getLogger(__name__)

pytestmark = [pytest.mark.sno, pytest.mark.gating, pytest.mark.arm64, pytest.mark.s390x, pytest.mark.conformance]


@pytest.fixture()
def crds(admin_client):
    target_suffixes = (Resource.ApiGroup.KUBEVIRT_IO, Resource.ApiGroup.NMSTATE_IO)
    return [crd for crd in CustomResourceDefinition.get(dyn_client=admin_client) if crd.name.endswith(target_suffixes)]


@pytest.mark.polarion("CNV-8263")
def test_crds_cluster_readers_role(crds):
    cluster_readers = "system:cluster-readers"
    unreadable_crds = []
    for crd in crds:
        can_read = check_output(shlex.split(f"oc adm policy who-can get {crd.name}"))
        if cluster_readers not in str(can_read):
            unreadable_crds.append(crd.name)

    assert not unreadable_crds, f"The following crds are missing {cluster_readers} role: {unreadable_crds}"
