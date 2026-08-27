"""RBAC helpers for granting cluster roles and namespaced role bindings.

This module holds shared helpers for creating RBAC resources (ClusterRole,
RoleBinding) used to grant subjects (users or service accounts) permissions.

It does NOT hold:
    - Authentication / login helpers (see utilities.infra.login_with_user_password)
    - Namespace creation (see utilities.infra.create_ns)
"""

from collections.abc import Generator
from contextlib import contextmanager

from kubernetes.dynamic import DynamicClient
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.role_binding import RoleBinding


@contextmanager
def create_cluster_role(
    client: DynamicClient, name: str, api_groups: list[str], verbs: list[str], permissions_to_resources: list[str]
) -> Generator:
    """
    Create cluster role
    """
    with ClusterRole(
        client=client,
        name=name,
        rules=[
            {
                "apiGroups": api_groups,
                "resources": permissions_to_resources,
                "verbs": verbs,
            },
        ],
    ) as cluster_role:
        yield cluster_role


@contextmanager
def create_role_binding(
    client: DynamicClient,
    name: str,
    namespace: str,
    subjects_kind: str,
    subjects_name: str,
    role_ref_kind: str,
    role_ref_name: str,
    subjects_namespace: str | None = None,
    subjects_api_group: str | None = None,
) -> Generator:
    """
    Create role binding
    """
    with RoleBinding(
        client=client,
        name=name,
        namespace=namespace,
        subjects_kind=subjects_kind,
        subjects_name=subjects_name,
        subjects_api_group=subjects_api_group,
        subjects_namespace=subjects_namespace,
        role_ref_kind=role_ref_kind,
        role_ref_name=role_ref_name,
    ) as role_binding:
        yield role_binding


@contextmanager
def set_permissions(
    client: DynamicClient,
    role_name: str,
    role_api_groups: list[str],
    verbs: list[str],
    permissions_to_resources: list[str],
    binding_name: str,
    namespace: str,
    subjects_name: str,
    subjects_kind: str = "User",
    subjects_api_group: str | None = None,
    subjects_namespace: str | None = None,
) -> Generator:
    with create_cluster_role(
        client=client,
        name=role_name,
        api_groups=role_api_groups,
        permissions_to_resources=permissions_to_resources,
        verbs=verbs,
    ) as cluster_role:
        with create_role_binding(
            client=client,
            name=binding_name,
            namespace=namespace,
            subjects_kind=subjects_kind,
            subjects_name=subjects_name,
            subjects_api_group=subjects_api_group,
            subjects_namespace=subjects_namespace,
            role_ref_kind=cluster_role.kind,
            role_ref_name=cluster_role.name,
        ):
            yield
