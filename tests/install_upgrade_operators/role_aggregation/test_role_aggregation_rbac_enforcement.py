"""
Role-based access control (RBAC) tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/CNV-63822-role-aggregation-opt-out.md

Markers:
    - post_upgrade
    - arm64

Preconditions:
    - Unprivileged user created via HTPasswd identity provider
    - Namespace for RBAC testing
"""

import pytest

__test__ = False


class TestRoleAggregationDisabled:
    """
    Tests for RBAC enforcement when role aggregation is disabled.

    Preconditions:
        - HyperConverged CR spec.roleAggregationStrategy set to "AggregateToDefault" (role aggregation enabled)
        - RoleBinding granting the unprivileged user the parametrized ClusterRole in the namespace
    """

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param("admin", marks=pytest.mark.polarion("CNV-16028")),
            pytest.param("edit", marks=pytest.mark.polarion("CNV-16262")),
            pytest.param("view", marks=pytest.mark.polarion("CNV-16263")),
        ],
    )
    def test_vm_list_forbidden_when_aggregation_disabled(self, role):
        """
        [NEGATIVE] Test that an unprivileged user with a standard OpenShift role is forbidden
        from listing virtualization resources when role aggregation is disabled.

        Parametrize:
            - role: [admin, edit, view]

        Preconditions:
            - User can list VirtualMachine resources in the namespace successfully

        Steps:
            1. Set HyperConverged CR spec.roleAggregationStrategy to "Manual" (disable role aggregation)
            2. Wait for the kubevirt.io aggregated role labels to be removed from the user
            3. Attempt to list VirtualMachine resources in the namespace using the unprivileged
               user's credentials

        Expected:
            - Operation is rejected with a Forbidden error
        """


class TestRoleAggregationReenabledAccess:
    """
    Tests for role-specific access when role aggregation is re-enabled.

    Preconditions:
        - HyperConverged CR spec.roleAggregationStrategy set to "Manual" (role aggregation disabled)
        - RoleBinding granting the unprivileged user the respective ClusterRole in the namespace
        - HyperConverged CR spec.roleAggregationStrategy restored to "AggregateToDefault" (role aggregation re-enabled)
        - Wait for the kubevirt.io aggregated role labels to be added to the user
    """

    @pytest.mark.polarion("CNV-16029")
    def test_admin_can_delete_vm_collection_when_aggregation_reenabled(self):
        """
        Test that an unprivileged user with the admin role can perform a delete-collection
        call on VirtualMachine resources when role aggregation is enabled.

        Preconditions:
            - Unprivileged user with the admin ClusterRole bound in the namespace

        Steps:
            1. Issue a raw DELETE request to the VirtualMachine collection API endpoint
               using the unprivileged user's credentials

        Expected:
            - Delete-collection operation succeeds
        """

    @pytest.mark.polarion("CNV-16260")
    def test_edit_can_create_vm_dry_run_when_aggregation_reenabled(self):
        """
        Test that an unprivileged user with the edit role can create a VirtualMachine
        using a server-side dry-run when role aggregation is enabled.

        Preconditions:
            - Unprivileged user with the edit ClusterRole bound in the namespace

        Steps:
            1. Create a VirtualMachine using server-side dry-run with the unprivileged
               user's credentials

        Expected:
            - Dry-run create operation succeeds
        """

    @pytest.mark.polarion("CNV-16261")
    def test_view_can_list_vms_when_aggregation_reenabled(self):
        """
        Test that an unprivileged user with the view role can list VirtualMachine
        resources when role aggregation is enabled.

        Preconditions:
            - Unprivileged user with the view ClusterRole bound in the namespace

        Steps:
            1. List VirtualMachine resources in the namespace using the unprivileged user's credentials

        Expected:
            - VirtualMachine resources are listed successfully
        """
