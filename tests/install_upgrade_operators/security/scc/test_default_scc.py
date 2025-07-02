# -*- coding: utf-8 -*-

"""
Tests to check, the default Security Context Constraint
"""

import pytest
from ocp_resources.security_context_constraints import SecurityContextConstraints

pytestmark = [pytest.mark.post_upgrade, pytest.mark.gating, pytest.mark.arm64]


@pytest.fixture(scope="module")
def privileged_scc():
    yield SecurityContextConstraints(name="privileged")


@pytest.mark.polarion("CNV-4439")
@pytest.mark.s390x
def test_users_in_privileged_scc(privileged_scc):
    """
    Validate that Users in privileged SCC is not updated after installing CNV
    """
    assert len(privileged_scc.instance.users) == 2
    assert privileged_scc.instance.users[0] == "system:admin"
    assert privileged_scc.instance.users[1] == "system:serviceaccount:openshift-infra:build-controller"
