"""
Role-based access control (RBAC) tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/CNV-63822-role-aggregation-opt-out.md

Markers:
    - post_upgrade
"""

import pytest

__test__ = False

pytestmark = pytest.mark.post_upgrade


class TestRoleAggregationDisabledRBACEnforcement:
    """
    Tests for RBAC enforcement when role aggregation is disabled.

    Preconditions:
        - HyperConverged CR spec.roleAggregationStrategy set to "Manual" (role aggregation disabled)
        - Unprivileged user created via HTPasswd identity provider
    """

    @pytest.mark.polarion("CNV-16028")
    def test_vm_list_forbidden_when_aggregation_disabled(self):
        """
        [NEGATIVE] Test that an unprivileged user with a standard OpenShift role is forbidden
        from listing virtualization resources when role aggregation is disabled.

        Parametrize:
            - role: [admin, edit, view]

        Preconditions:
            - Namespace with a RoleBinding granting the unprivileged user the parametrized ClusterRole

        Steps:
            1. Attempt to list VirtualMachine resources in the namespace using the unprivileged
               user's credentials

        Expected:
            - Operation is rejected with a Forbidden error
        """


class TestRoleAggregationReenabledAccess:
    """
    Tests for role-specific access when role aggregation is enabled.

    Preconditions:
        - HyperConverged CR spec.roleAggregationStrategy set to "AggregateToDefault" (role aggregation enabled)
        - Unprivileged user created via HTPasswd identity provider
    """

    @pytest.mark.polarion("CNV-16029")
    def test_admin_can_delete_vm_collection_when_aggregation_reenabled(self):
        """
        Test that an unprivileged user with the admin role can perform a delete-collection
        call on VirtualMachine resources when role aggregation is enabled.

        Preconditions:
            - Namespace with a RoleBinding granting the unprivileged user the admin ClusterRole

        Steps:
            1. Issue a raw DELETE request to the VirtualMachine collection API endpoint
               using the unprivileged user's credentials

        Expected:
            - Delete-collection operation succeeds
        """

    @pytest.mark.polarion("CNV-16030")
    def test_edit_can_create_vm_dry_run_when_aggregation_reenabled(self):
        """
        Test that an unprivileged user with the edit role can create a VirtualMachine
        using a server-side dry-run when role aggregation is enabled.

        Preconditions:
            - Namespace with a RoleBinding granting the unprivileged user the edit ClusterRole

        Steps:
            1. Create a VirtualMachine using server-side dry-run with the unprivileged
               user's credentials

        Expected:
            - Dry-run create operation succeeds
        """

    @pytest.mark.polarion("CNV-16031")
    def test_view_can_list_vms_when_aggregation_reenabled(self):
        """
        Test that an unprivileged user with the view role can list VirtualMachine
        resources when role aggregation is enabled.

        Preconditions:
            - Namespace with a RoleBinding granting the unprivileged user the view ClusterRole

        Steps:
            1. List VirtualMachine resources in the namespace using the unprivileged user's credentials

        Expected:
            - VirtualMachine resources are listed successfully
        """
