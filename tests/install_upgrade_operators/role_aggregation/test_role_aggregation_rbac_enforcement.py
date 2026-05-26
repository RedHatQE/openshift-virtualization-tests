"""
Tests for RBAC enforcement when role aggregation is disabled.

STP: https://issues.redhat.com/browse/CNV-63822
"""

import pytest

__test__ = False


class TestRoleAggregationDisabledRBACEnforcement:
    """
    Tests for RBAC enforcement when role aggregation is disabled.

    STP: https://issues.redhat.com/browse/CNV-63822

    Preconditions:
        - OpenShift Virtualization installed
        - HyperConverged CR spec.roleAggregationStrategy set to "Manual" (role aggregation disabled)
        - Unprivileged user created via HTPasswd identity provider
    """

    @pytest.mark.polarion("CNV-63826")
    def test_vm_list_forbidden_when_aggregation_disabled(self):
        """
        [NEGATIVE] Test that an unprivileged user with a standard OpenShift role is forbidden
        from listing virtualization resources when role aggregation is disabled.

        Parametrize:
            - role: [admin, edit, view]

        Preconditions:
            - Unprivileged user created via HTPasswd identity provider
            - Namespace with a RoleBinding granting the unprivileged user the parametrized ClusterRole

        Steps:
            1. Attempt to list VirtualMachine resources in the namespace using the unprivileged
               user's credentials

        Expected:
            - Operation is rejected with a Forbidden error
        """


class TestRoleAggregationReenabledAccess:
    """
    Tests for access restoration when role aggregation is re-enabled.

    STP: https://issues.redhat.com/browse/CNV-63822

    Preconditions:
        - OpenShift Virtualization installed
        - HyperConverged CR spec.roleAggregationStrategy changed from "Manual" to
          "AggregateToDefault" (role aggregation re-enabled)
        - Unprivileged user created via HTPasswd identity provider
    """

    @pytest.mark.polarion("CNV-63829")
    def test_access_restored_when_aggregation_reenabled(self):
        """
        Test that an unprivileged user with a standard OpenShift role can list virtualization
        resources when role aggregation is re-enabled.

        Parametrize:
            - role: [admin, edit, view]

        Preconditions:
            - Unprivileged user created via HTPasswd identity provider
            - Namespace with a RoleBinding granting the unprivileged user the parametrized ClusterRole

        Steps:
            1. Attempt to list VirtualMachine resources in the namespace using the unprivileged
               user's credentials

        Expected:
            - VirtualMachine resources are listed successfully
        """
