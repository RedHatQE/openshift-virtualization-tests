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
    LOGGER.info(f"Waiting for aggregation labels: expected_present={expected_present}")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=10,
        func=aggregation_labels_match_expected_state,
        admin_client=admin_client,
        expected_present=expected_present,
    ):
        if sample:
            break
    LOGGER.info(f"Aggregation labels match expected state: expected_present={expected_present}")


def can_list_vms(client: DynamicClient, namespace_name: str) -> bool:
    """Check if listing VirtualMachines succeeds.

    Args:
        client: DynamicClient to test access with.
        namespace_name: Namespace to list VMs in.

    Returns:
        True if listing succeeds, False if ForbiddenError is raised.
    """
    try:
        list(VirtualMachine.get(client=client, namespace=namespace_name))
        return True
    except ForbiddenError:
        return False


def wait_for_vm_list_permission(client: DynamicClient, namespace_name: str, allowed: bool) -> None:
    """Wait for VM list permission to reach the expected state.

    Args:
        client: DynamicClient to test access with.
        namespace_name: Namespace to list VMs in.
        allowed: True to wait for access, False to wait for forbidden.
    """
    LOGGER.info(f"Waiting for VM list access: allowed={allowed}")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=2,
        func=can_list_vms,
        client=client,
        namespace_name=namespace_name,
    ):
        if sample == allowed:
            LOGGER.info(f"VM list access reached expected state: allowed={allowed}")
            break


def unprivileged_role_binding(
    admin_client: DynamicClient,
    namespace_name: str,
    role_name: str,
) -> Generator[None]:
    """Create a RoleBinding granting a ClusterRole to the unprivileged user.

    Args:
        admin_client: Admin DynamicClient for API access.
        namespace_name: Namespace where the RoleBinding is created.
        role_name: ClusterRole name to bind (admin, edit, or view).

    Yields:
        None while the RoleBinding exists.
    """
    with RoleBinding(
        name=f"test-role-bind-{role_name}",
        namespace=namespace_name,
        client=admin_client,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        subjects_namespace=namespace_name,
        role_ref_kind="ClusterRole",
        role_ref_name=role_name,
    ):
        yield


def ensure_aggregation_enabled(admin_client: DynamicClient, hyperconverged_resource: HyperConverged) -> None:
    """Verify roleAggregationStrategy is AggregateToDefault and aggregation labels are present.

    Checks the current strategy value and patches it if not AggregateToDefault,
    then waits for aggregation labels to be present on all kubevirt.io ClusterRoles.

    Args:
        admin_client: Admin DynamicClient for API access.
        hyperconverged_resource: HyperConverged CR to check and patch.
    """
    current_strategy = hyperconverged_resource.instance.spec.get("roleAggregationStrategy", "AggregateToDefault")
    if current_strategy != "AggregateToDefault":
        LOGGER.info(f"roleAggregationStrategy is {current_strategy}, setting to AggregateToDefault")
        editor = ResourceEditorValidateHCOReconcile(
            patches={hyperconverged_resource: {"spec": {"roleAggregationStrategy": "AggregateToDefault"}}},
            list_resource_reconcile=[KubeVirt],
            wait_for_reconcile_post_update=True,
            admin_client=admin_client,
        )
        editor.update(backup_resources=False)
    wait_for_aggregation_labels(admin_client=admin_client, expected_present=True)
