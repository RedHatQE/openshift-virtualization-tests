"""
Role Aggregation Opt-Out RBAC Enforcement Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/CNV-63822-role-aggregation-opt-out.md

Markers:
    - post_upgrade
    - arm64

Preconditions:
    - Unprivileged user created via HTPasswd identity provider
    - Namespace for RBAC testing
"""

import pytest
from kubernetes.dynamic.exceptions import ForbiddenError
from ocp_resources.virtual_machine import VirtualMachine

pytestmark = [pytest.mark.post_upgrade, pytest.mark.arm64]


class TestRoleAggregationDisabled:
    """
    Tests for RBAC enforcement when role aggregation is disabled.

    Preconditions:
        - HyperConverged CR spec.roleAggregationStrategy set to "AggregateToDefault"
          (role aggregation enabled)
        - RoleBinding granting the unprivileged user the parametrized ClusterRole in the namespace
    """

    @pytest.mark.parametrize(
        "disabled_aggregation_with_role",
        [
            pytest.param("admin", marks=pytest.mark.polarion("CNV-16028")),
            pytest.param("edit", marks=pytest.mark.polarion("CNV-16262")),
            pytest.param("view", marks=pytest.mark.polarion("CNV-16263")),
        ],
        indirect=True,
    )
    def test_vm_list_forbidden_when_aggregation_disabled(
        self, disabled_aggregation_with_role, unprivileged_client, namespace
    ):
        """
        [NEGATIVE] Test that an unprivileged user with a standard OpenShift role is forbidden
        from listing virtualization resources when role aggregation is disabled.

        Parametrize:
            - role: [admin, edit, view]

        Preconditions:
            - User can list VirtualMachine resources in the namespace successfully

        Steps:
            1. Set HyperConverged CR spec.roleAggregationStrategy to "Manual"
               (disable role aggregation)
            2. Wait for the aggregation labels to be removed from the kubevirt.io ClusterRoles
            3. Attempt to list VirtualMachine resources in the namespace using the unprivileged
               user's credentials

        Expected:
            - Operation is rejected with a Forbidden error
        """
        with pytest.raises(ForbiddenError):
            list(VirtualMachine.get(client=unprivileged_client, namespace=namespace.name))


class TestRoleAggregationReenabledAccess:
    """
    Tests for role-specific access when role aggregation is re-enabled.

    Preconditions:
        - HyperConverged CR spec.roleAggregationStrategy set to "Manual"
          (role aggregation disabled)
        - RoleBinding granting the unprivileged user the respective ClusterRole in the namespace
        - HyperConverged CR spec.roleAggregationStrategy restored to "AggregateToDefault"
          (role aggregation re-enabled)
        - Aggregation labels restored on kubevirt.io ClusterRoles
    """

    @pytest.mark.parametrize(
        "reenabled_aggregation_with_role",
        [pytest.param("admin", marks=pytest.mark.polarion("CNV-16029"))],
        indirect=True,
    )
    def test_admin_can_delete_vm_collection_when_aggregation_reenabled(
        self, reenabled_aggregation_with_role, vm_collection_resource_for_unprivileged_client, namespace
    ):
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
        vm_collection_resource_for_unprivileged_client.delete(
            namespace=namespace.name, label_selector="rbac-test=nonexistent"
        )

    @pytest.mark.parametrize(
        "reenabled_aggregation_with_role",
        [pytest.param("edit", marks=pytest.mark.polarion("CNV-16260"))],
        indirect=True,
    )
    def test_edit_can_create_vm_dry_run_when_aggregation_reenabled(self, reenabled_aggregation_with_role, dry_run_vm):
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
        dry_run_vm.create()

    @pytest.mark.parametrize(
        "reenabled_aggregation_with_role",
        [pytest.param("view", marks=pytest.mark.polarion("CNV-16261"))],
        indirect=True,
    )
    def test_view_can_list_vms_when_aggregation_reenabled(
        self, reenabled_aggregation_with_role, unprivileged_client, namespace
    ):
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
        list(VirtualMachine.get(client=unprivileged_client, namespace=namespace.name))
