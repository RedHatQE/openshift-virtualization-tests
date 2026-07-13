from __future__ import annotations

import logging
from collections.abc import Generator
from typing import TYPE_CHECKING

from kubernetes.dynamic.exceptions import ForbiddenError
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.role_binding import RoleBinding
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutSampler

from utilities.constants.pytest import UNPRIVILEGED_USER
from utilities.constants.timeouts import TIMEOUT_1MIN, TIMEOUT_5MIN
from utilities.hco import ResourceEditorValidateHCOReconcile

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.hyperconverged import HyperConverged

LOGGER = logging.getLogger(__name__)

KUBEVIRT_AGGREGATION_ROLES: dict[str, str] = {
    "kubevirt.io:admin": "rbac.authorization.k8s.io/aggregate-to-admin",
    "kubevirt.io:edit": "rbac.authorization.k8s.io/aggregate-to-edit",
    "kubevirt.io:view": "rbac.authorization.k8s.io/aggregate-to-view",
}


def aggregation_labels_match_expected_state(admin_client: DynamicClient, expected_present: bool) -> bool:
    """Check if aggregation labels on kubevirt.io ClusterRoles match expected state.

    Args:
        admin_client: Admin DynamicClient for API access.
        expected_present: True to check labels exist, False to check they are absent.

    Returns:
        True if all ClusterRoles match the expected label state.
    """
    for role_name, label_key in KUBEVIRT_AGGREGATION_ROLES.items():
        cluster_role = ClusterRole(name=role_name, client=admin_client)
        labels = cluster_role.instance.metadata.labels or {}
        label_present = labels.get(label_key) == "true"
        if label_present != expected_present:
            LOGGER.warning(
                f"Label {label_key} on {role_name}: present={label_present}, expected_present={expected_present}"
            )
            return False
    return True


def wait_for_aggregation_labels(admin_client: DynamicClient, expected_present: bool) -> None:
    """Wait for aggregation labels on kubevirt.io ClusterRoles to reach expected state.

    Args:
        admin_client: Admin DynamicClient for API access.
        expected_present: True to wait for labels to appear, False to wait for removal.
    """
    state_description = "present" if expected_present else "absent"
    LOGGER.info(f"Waiting for aggregation labels to be {state_description} on kubevirt.io ClusterRoles")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=10,
        func=aggregation_labels_match_expected_state,
        admin_client=admin_client,
        expected_present=expected_present,
    ):
        if sample:
            break
    LOGGER.info(f"Aggregation labels are {state_description} on all kubevirt.io ClusterRoles")


def vm_list_is_forbidden(client: DynamicClient, namespace_name: str) -> bool:
    """Check if listing VirtualMachines raises ForbiddenError.

    Args:
        client: DynamicClient to test access with.
        namespace_name: Namespace to list VMs in.

    Returns:
        True if ForbiddenError is raised, False if listing succeeds.
    """
    try:
        list(VirtualMachine.get(client=client, namespace=namespace_name))
        return False
    except ForbiddenError:
        return True


def wait_for_vm_list_access(client: DynamicClient, namespace_name: str) -> None:
    """Wait for an unprivileged user to be able to list VirtualMachines.

    Args:
        client: DynamicClient to test access with.
        namespace_name: Namespace to list VMs in.
    """
    LOGGER.info("Waiting for VM list access to propagate")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=2,
        func=vm_list_is_forbidden,
        client=client,
        namespace_name=namespace_name,
    ):
        if not sample:
            break


def disabled_aggregation_with_role_binding(
    admin_client: DynamicClient,
    unprivileged_client: DynamicClient,
    namespace_name: str,
    hyperconverged_resource: HyperConverged,
    role_name: str,
) -> Generator[None]:
    """Create role binding, disable aggregation, wait for RBAC revocation.

    Args:
        admin_client: Admin DynamicClient for API access.
        unprivileged_client: Unprivileged DynamicClient to verify access changes.
        namespace_name: Namespace where the RoleBinding is created.
        hyperconverged_resource: HyperConverged CR to patch.
        role_name: ClusterRole name to bind (admin, edit, or view).
    """
    cluster_role = ClusterRole(name=role_name, client=admin_client, ensure_exists=True)
    with RoleBinding(
        name=f"test-role-bind-{role_name}",
        namespace=namespace_name,
        client=admin_client,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_namespace=namespace_name,
        role_ref_kind=cluster_role.kind,
        role_ref_name=cluster_role.name,
    ):
        wait_for_vm_list_access(client=unprivileged_client, namespace_name=namespace_name)

        with ResourceEditorValidateHCOReconcile(
            patches={hyperconverged_resource: {"spec": {"roleAggregationStrategy": "Manual"}}},
            list_resource_reconcile=[KubeVirt],
            wait_for_reconcile_post_update=True,
        ):
            wait_for_aggregation_labels(admin_client=admin_client, expected_present=False)
            LOGGER.info(f"Waiting for {role_name} role de-aggregation to propagate")
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_1MIN,
                sleep=2,
                func=vm_list_is_forbidden,
                client=unprivileged_client,
                namespace_name=namespace_name,
            ):
                if sample:
                    break
            LOGGER.info(f"Aggregation disabled with {role_name} RoleBinding; user access revoked")
            yield


def reenabled_aggregation_with_role_binding(
    admin_client: DynamicClient,
    namespace_name: str,
    hyperconverged_resource: HyperConverged,
    role_name: str,
) -> Generator[None]:
    """Disable aggregation, create role binding, re-enable aggregation, wait for labels.

    Follows the precondition order: Manual → RoleBinding → AggregateToDefault → labels restored.

    Args:
        admin_client: Admin DynamicClient for API access.
        namespace_name: Namespace where the RoleBinding is created.
        hyperconverged_resource: HyperConverged CR to patch.
        role_name: ClusterRole name to bind (admin, edit, or view).
    """
    LOGGER.info(f"Setting roleAggregationStrategy to Manual for {role_name} re-enable test")
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource: {"spec": {"roleAggregationStrategy": "Manual"}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        wait_for_aggregation_labels(admin_client=admin_client, expected_present=False)
        LOGGER.info(f"Creating RoleBinding for {role_name} role")
        cluster_role = ClusterRole(name=role_name, client=admin_client, ensure_exists=True)
        with RoleBinding(
            name=f"test-role-bind-{role_name}",
            namespace=namespace_name,
            client=admin_client,
            subjects_kind="User",
            subjects_name=UNPRIVILEGED_USER,
            subjects_namespace=namespace_name,
            role_ref_kind=cluster_role.kind,
            role_ref_name=cluster_role.name,
        ):
            LOGGER.info("Restoring roleAggregationStrategy to AggregateToDefault")
            with ResourceEditorValidateHCOReconcile(
                patches={hyperconverged_resource: {"spec": {"roleAggregationStrategy": "AggregateToDefault"}}},
                list_resource_reconcile=[KubeVirt],
                wait_for_reconcile_post_update=True,
            ):
                wait_for_aggregation_labels(admin_client=admin_client, expected_present=True)
                LOGGER.info(f"Role aggregation re-enabled with {role_name} RoleBinding; labels confirmed present")
                yield
