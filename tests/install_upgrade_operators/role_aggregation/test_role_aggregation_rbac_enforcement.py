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

import logging

import pytest
from kubernetes.dynamic.exceptions import ForbiddenError
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.role_binding import RoleBinding
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutSampler

from tests.install_upgrade_operators.role_aggregation.utils import vm_list_is_forbidden, wait_for_aggregation_labels
from utilities.constants.pytest import UNPRIVILEGED_USER
from utilities.constants.timeouts import TIMEOUT_1MIN, TIMEOUT_30SEC
from utilities.hco import ResourceEditorValidateHCOReconcile

LOGGER = logging.getLogger(__name__)

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
        "role",
        [
            pytest.param("admin", marks=pytest.mark.polarion("CNV-16028")),
            pytest.param("edit", marks=pytest.mark.polarion("CNV-16262")),
            pytest.param("view", marks=pytest.mark.polarion("CNV-16263")),
        ],
    )
    def test_vm_list_forbidden_when_aggregation_disabled(
        self, role, admin_client, unprivileged_client, namespace, hyperconverged_resource_scope_class
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
        cluster_role = ClusterRole(name=role, client=admin_client, ensure_exists=True)
        with RoleBinding(
            name=f"test-role-bind-{role}",
            namespace=namespace.name,
            client=admin_client,
            subjects_kind="User",
            subjects_name=UNPRIVILEGED_USER,
            subjects_namespace=namespace.name,
            role_ref_kind=cluster_role.kind,
            role_ref_name=cluster_role.name,
        ):
            LOGGER.info(f"Baseline: waiting for {role} role RBAC propagation before testing")
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_30SEC,
                sleep=2,
                func=lambda: list(VirtualMachine.get(client=unprivileged_client, namespace=namespace.name)) is not None,
                exceptions_dict={ForbiddenError: []},
            ):
                if sample:
                    break

            with ResourceEditorValidateHCOReconcile(
                patches={hyperconverged_resource_scope_class: {"spec": {"roleAggregationStrategy": "Manual"}}},
                list_resource_reconcile=[KubeVirt],
                wait_for_reconcile_post_update=True,
            ):
                wait_for_aggregation_labels(admin_client=admin_client, expected_present=False)
                LOGGER.info(f"Waiting for {role} role de-aggregation to propagate")
                for sample in TimeoutSampler(
                    wait_timeout=TIMEOUT_1MIN,
                    sleep=2,
                    func=vm_list_is_forbidden,
                    client=unprivileged_client,
                    namespace_name=namespace.name,
                ):
                    if sample:
                        break
                LOGGER.info(f"Asserting user with {role} role is forbidden from listing VMs")
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
        - Wait for the aggregation labels to be restored on the kubevirt.io ClusterRoles
    """

    @pytest.mark.polarion("CNV-16029")
    @pytest.mark.usefixtures("admin_reenabled_aggregation")
    def test_admin_can_delete_vm_collection_when_aggregation_reenabled(self, unprivileged_client, namespace):
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
        vm_resource = unprivileged_client.resources.get(api_version="kubevirt.io/v1", kind="VirtualMachine")
        vm_resource.delete(namespace=namespace.name, label_selector="rbac-test=nonexistent")
        LOGGER.info("Admin user successfully performed delete-collection on VirtualMachines")

    @pytest.mark.polarion("CNV-16260")
    @pytest.mark.usefixtures("edit_reenabled_aggregation")
    def test_edit_can_create_vm_dry_run_when_aggregation_reenabled(self, unprivileged_client, namespace):
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
        vm = VirtualMachine(
            name="rbac-dry-run-vm",
            namespace=namespace.name,
            client=unprivileged_client,
            body={
                "spec": {
                    "running": False,
                    "template": {
                        "spec": {
                            "domain": {
                                "devices": {},
                                "resources": {
                                    "requests": {
                                        "memory": "64Mi",
                                    },
                                },
                            },
                        },
                    },
                },
            },
            dry_run=True,
        )
        vm.create()
        LOGGER.info("Edit user successfully performed dry-run VM creation")

    @pytest.mark.polarion("CNV-16261")
    @pytest.mark.usefixtures("view_reenabled_aggregation")
    def test_view_can_list_vms_when_aggregation_reenabled(self, unprivileged_client, namespace):
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
        LOGGER.info("View user successfully listed VirtualMachines")
