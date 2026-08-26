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

from tests.install_upgrade_operators.role_aggregation.utils import wait_for_vm_list_permission

pytestmark = [pytest.mark.post_upgrade, pytest.mark.arm64]


@pytest.mark.usefixtures("admin_role_binding")
class TestRoleAggregationAdmin:
    """
    Tests for admin role RBAC behavior across aggregation state changes.

    The re-enabled test depends on the disabled test; if the disabled test
    failed, the aggregation state may be inconsistent for the re-enabled flow.

    Preconditions:
        - RoleBinding granting the unprivileged user the admin ClusterRole
          in the namespace
    """

    @pytest.mark.polarion("CNV-16028")
    @pytest.mark.dependency(name="test_disabled_admin")
    @pytest.mark.usefixtures("aggregation_disabled")
    def test_admin_forbidden_when_aggregation_disabled(self, unprivileged_client, namespace):
        """
        [NEGATIVE] Test that an unprivileged user with the admin role is forbidden
        from listing virtualization resources when role aggregation is disabled.

        Preconditions:
            - HyperConverged CR spec.roleAggregationStrategy set to "Manual"
              (role aggregation disabled)

        Steps:
            1. Attempt to list VirtualMachine resources in the namespace using
               the unprivileged user's credentials

        Expected:
            - Operation is rejected with a Forbidden error
        """
        wait_for_vm_list_permission(client=unprivileged_client, namespace_name=namespace.name, is_allowed=False)

    @pytest.mark.polarion("CNV-16029")
    @pytest.mark.dependency(depends=["test_disabled_admin"])
    @pytest.mark.usefixtures("aggregation_reenabled")
    def test_admin_can_delete_vm_collection_when_aggregation_reenabled(
        self, unprivileged_client, vm_collection_resource_for_unprivileged_client, namespace
    ):
        """
        Test that an unprivileged user with the admin role can perform a delete-collection
        call on VirtualMachine resources when role aggregation is re-enabled.

        Preconditions:
            - HyperConverged CR spec.roleAggregationStrategy restored to
              "AggregateToDefault"

        Steps:
            1. Issue a raw DELETE request to the VirtualMachine collection API endpoint
               using the unprivileged user's credentials

        Expected:
            - Delete-collection operation succeeds
        """
        vm_collection_resource_for_unprivileged_client.delete(
            namespace=namespace.name, label_selector="rbac-test=nonexistent"
        )


@pytest.mark.usefixtures("edit_role_binding")
class TestRoleAggregationEdit:
    """
    Tests for edit role RBAC behavior across aggregation state changes.

    The re-enabled test depends on the disabled test; if the disabled test
    failed, the aggregation state may be inconsistent for the re-enabled flow.

    Preconditions:
        - RoleBinding granting the unprivileged user the edit ClusterRole
          in the namespace
    """

    @pytest.mark.polarion("CNV-16262")
    @pytest.mark.dependency(name="test_disabled_edit")
    @pytest.mark.usefixtures("aggregation_disabled")
    def test_edit_forbidden_when_aggregation_disabled(self, unprivileged_client, namespace):
        """
        [NEGATIVE] Test that an unprivileged user with the edit role is forbidden
        from listing virtualization resources when role aggregation is disabled.

        Preconditions:
            - HyperConverged CR spec.roleAggregationStrategy set to "Manual"
              (role aggregation disabled)

        Steps:
            1. Attempt to list VirtualMachine resources in the namespace using
               the unprivileged user's credentials

        Expected:
            - Operation is rejected with a Forbidden error
        """
        wait_for_vm_list_permission(client=unprivileged_client, namespace_name=namespace.name, is_allowed=False)

    @pytest.mark.polarion("CNV-16260")
    @pytest.mark.dependency(depends=["test_disabled_edit"])
    @pytest.mark.usefixtures("aggregation_reenabled")
    def test_edit_can_create_vm_dry_run_when_aggregation_reenabled(self, unprivileged_client, namespace, dry_run_vm):
        """
        Test that an unprivileged user with the edit role can create a VirtualMachine
        using a server-side dry-run when role aggregation is re-enabled.

        Preconditions:
            - HyperConverged CR spec.roleAggregationStrategy restored to
              "AggregateToDefault"

        Steps:
            1. Create a VirtualMachine using server-side dry-run with the unprivileged
               user's credentials

        Expected:
            - Dry-run create operation succeeds
        """
        dry_run_vm.create()


@pytest.mark.usefixtures("view_role_binding")
class TestRoleAggregationView:
    """
    Tests for view role RBAC behavior across aggregation state changes.

    The re-enabled test depends on the disabled test; if the disabled test
    failed, the aggregation state may be inconsistent for the re-enabled flow.

    Preconditions:
        - RoleBinding granting the unprivileged user the view ClusterRole
          in the namespace
    """

    @pytest.mark.polarion("CNV-16263")
    @pytest.mark.dependency(name="test_disabled_view")
    @pytest.mark.usefixtures("aggregation_disabled")
    def test_view_forbidden_when_aggregation_disabled(self, unprivileged_client, namespace):
        """
        [NEGATIVE] Test that an unprivileged user with the view role is forbidden
        from listing virtualization resources when role aggregation is disabled.

        Preconditions:
            - HyperConverged CR spec.roleAggregationStrategy set to "Manual"
              (role aggregation disabled)

        Steps:
            1. Attempt to list VirtualMachine resources in the namespace using
               the unprivileged user's credentials

        Expected:
            - Operation is rejected with a Forbidden error
        """
        wait_for_vm_list_permission(client=unprivileged_client, namespace_name=namespace.name, is_allowed=False)

    @pytest.mark.polarion("CNV-16261")
    @pytest.mark.dependency(depends=["test_disabled_view"])
    @pytest.mark.usefixtures("aggregation_reenabled")
    def test_view_can_list_vms_when_aggregation_reenabled(self, unprivileged_client, namespace):
        """
        Test that an unprivileged user with the view role can list VirtualMachine
        resources when role aggregation is re-enabled.

        Preconditions:
            - HyperConverged CR spec.roleAggregationStrategy restored to
              "AggregateToDefault"

        Steps:
            1. List VirtualMachine resources in the namespace using the unprivileged
               user's credentials

        Expected:
            - VirtualMachine resources are listed successfully
        """
        wait_for_vm_list_permission(client=unprivileged_client, namespace_name=namespace.name, is_allowed=True)
