from __future__ import annotations

import logging
from collections.abc import Generator
from typing import TYPE_CHECKING

from kubernetes.dynamic.exceptions import ForbiddenError
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.role_binding import RoleBinding
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutSampler

from utilities.constants.pytest import UNPRIVILEGED_USER
from utilities.constants.timeouts import TIMEOUT_1MIN, TIMEOUT_5MIN, TIMEOUT_5SEC, TIMEOUT_10SEC

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
LOGGER = logging.getLogger(__name__)

KUBEVIRT_AGGREGATION_LEVELS = ("admin", "edit", "view")


def get_kubevirt_aggregation_roles(admin_client: DynamicClient) -> dict[str, str]:
    """Build mapping of kubevirt.io ClusterRole names to their aggregation label keys.

    Reads the aggregationRule from the built-in admin/edit/view ClusterRoles
    to discover the label key each role aggregates on.

    Args:
        admin_client: Admin DynamicClient for API access.

    Returns:
        Dict mapping kubevirt.io role name to its aggregation label key.
    """
    roles = {}
    for level in KUBEVIRT_AGGREGATION_LEVELS:
        built_in_role = ClusterRole(name=level, client=admin_client)
        selectors = built_in_role.instance.aggregationRule.clusterRoleSelectors
        label_key, _ = next(iter(selectors[0].matchLabels))
        roles[f"kubevirt.io:{level}"] = label_key
    return roles


def aggregation_labels_match_expected_state(
    admin_client: DynamicClient, should_be_present: bool, aggregation_roles: dict[str, str]
) -> bool:
    """Check if aggregation labels on kubevirt.io ClusterRoles match expected state.

    Args:
        admin_client: Admin DynamicClient for API access.
        should_be_present: True to check labels exist, False to check they are absent.
        aggregation_roles: Mapping of kubevirt.io role name to aggregation label key.

    Returns:
        True if all ClusterRoles match the expected label state.
    """
    for role_name, label_key in aggregation_roles.items():
        labels = ClusterRole(name=role_name, client=admin_client).instance.metadata.labels or {}
        label_found = labels.get(label_key) == "true"
        if label_found != should_be_present:
            state = "present" if label_found else "absent"
            expected = "present" if should_be_present else "absent"
            LOGGER.warning(f"Label {label_key} on {role_name} is {state}, expected {expected}")
            return False
    return True


def wait_for_aggregation_labels(admin_client: DynamicClient, should_be_present: bool) -> None:
    """Wait for aggregation labels on kubevirt.io ClusterRoles to reach expected state.

    Args:
        admin_client: Admin DynamicClient for API access.
        should_be_present: True to wait for labels to appear, False to wait for removal.
    """
    aggregation_roles = get_kubevirt_aggregation_roles(admin_client=admin_client)
    LOGGER.info(f"Waiting for aggregation labels: should_be_present={should_be_present}")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_10SEC,
        func=aggregation_labels_match_expected_state,
        admin_client=admin_client,
        should_be_present=should_be_present,
        aggregation_roles=aggregation_roles,
    ):
        if sample:
            break
    LOGGER.info(f"Aggregation labels match expected state: should_be_present={should_be_present}")


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
        sleep=TIMEOUT_5SEC,
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
