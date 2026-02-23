"""
Tests to check, the default Security Context Constraint
"""

import pytest
from ocp_resources.security_context_constraints import SecurityContextConstraints

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.gating,
    pytest.mark.arm64,
    pytest.mark.s390x,
    pytest.mark.skip_must_gather_collection,
]


@pytest.fixture(scope="module")
def privileged_scc(admin_client):
    yield SecurityContextConstraints(name="privileged", client=admin_client)


@pytest.mark.polarion("CNV-4439")
def test_users_in_privileged_scc(privileged_scc):
    """
    Validate that Users in privileged SCC is not updated after installing CNV
    """
    assert len(privileged_scc.instance.users) == 2
    assert privileged_scc.instance.users[0] == "system:admin"
    assert privileged_scc.instance.users[1] == "system:serviceaccount:openshift-infra:build-controller"
