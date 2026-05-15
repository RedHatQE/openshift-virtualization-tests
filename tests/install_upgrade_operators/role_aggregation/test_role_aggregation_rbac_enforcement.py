"""
Tests for RBAC enforcement when role aggregation is disabled.

STP: https://issues.redhat.com/browse/CNV-63822
"""

import pytest

__test__ = False


class TestRoleAggregationRBACEnforcement:
    """
    Tests for RBAC enforcement when role aggregation is disabled.

    STP: https://issues.redhat.com/browse/CNV-63822

    Preconditions:
        - OpenShift Virtualization installed
        - HyperConverged CR spec.roleAggregationStrategy set to "Manual" (role aggregation disabled)
        - Unprivileged user created via HTPasswd identity provider
    """

    @pytest.mark.polarion("CNV-63826")
    def test_admin_role_forbidden_when_aggregation_disabled(self):
        """
        [NEGATIVE] Test that an unprivileged user with project admin role is forbidden from
        performing virtualization admin actions when role aggregation is disabled.

        Preconditions:
            - Unprivileged user created via HTPasswd identity provider
            - Namespace where the unprivileged user has admin role
            - HyperConverged CR spec.roleAggregationStrategy set to "Manual"

        Steps:
            1. Attempt to create a VirtualMachine in the namespace using the unprivileged
               user's credentials

        Expected:
            - Operation is rejected with a Forbidden error
        """

    @pytest.mark.polarion("CNV-63827")
    def test_edit_role_forbidden_when_aggregation_disabled(self):
        """
        [NEGATIVE] Test that an unprivileged user with edit role is forbidden from performing
        virtualization edit actions when role aggregation is disabled.

        Preconditions:
            - Unprivileged user created via HTPasswd identity provider
            - Namespace with a RoleBinding granting the unprivileged user the edit ClusterRole
            - HyperConverged CR spec.roleAggregationStrategy set to "Manual"

        Steps:
            1. Attempt to create a VirtualMachine in the namespace using the unprivileged
               user's credentials

        Expected:
            - Operation is rejected with a Forbidden error
        """

    @pytest.mark.polarion("CNV-63828")
    def test_view_role_forbidden_when_aggregation_disabled(self):
        """
        [NEGATIVE] Test that an unprivileged user with view role is forbidden from performing
        virtualization view actions when role aggregation is disabled.

        Preconditions:
            - Unprivileged user created via HTPasswd identity provider
            - Namespace with a RoleBinding granting the unprivileged user the view ClusterRole
            - HyperConverged CR spec.roleAggregationStrategy set to "Manual"

        Steps:
            1. Attempt to list VirtualMachine resources in the namespace using the unprivileged
               user's credentials

        Expected:
            - Operation is rejected with a Forbidden error
        """

    @pytest.mark.polarion("CNV-63829")
    def test_access_restored_when_aggregation_reenabled(self):
        """
        Test that virtualization access is restored for unprivileged users when role aggregation
        is re-enabled after being disabled.

        Preconditions:
            - Unprivileged user created via HTPasswd identity provider
            - Namespace where the unprivileged user has admin role
            - HyperConverged CR spec.roleAggregationStrategy was set to "Manual"
              (role aggregation disabled)
            - HyperConverged CR spec.roleAggregationStrategy changed to "AggregateToDefault"
              (role aggregation re-enabled)

        Steps:
            1. Attempt to create a VirtualMachine in the namespace using the unprivileged
               user's credentials

        Expected:
            - VirtualMachine is created successfully
        """
