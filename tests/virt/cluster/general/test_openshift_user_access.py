import logging
import subprocess

import pytest
from ocp_resources.namespace import Namespace
from ocp_resources.role_binding import RoleBinding

from utilities.constants import UNPRIVILEGED_USER

LOGGER = logging.getLogger(__name__)


def verify_permissions(resource: str, expected_result: str, namespace: Namespace, verbs: str | None = None):
    """
    Verify user permissions on a resource or subresource.

    Args:
        resource: The resource or subresource path (e.g., 'virtualmachines', 'virtualmachineinstances/pause')
        expected_result: 'yes' if user should have permissions, 'no' if not
        namespace: The namespace to test in
        verbs: List of verbs to test. If None, tests all 8 standard verbs

    Raises:
        AssertionError: If any permission check doesn't match the expected result
    """
    verbs = (
        ["get", "list", "watch", "delete", "create", "update", "patch", "deletecollection"]
        if verbs is None
        else [verbs]
    )

    for verb in verbs:
        cmd = ["oc", "auth", "can-i", "--as", UNPRIVILEGED_USER, verb, resource, "-n", namespace.name]
        result = subprocess.run(cmd, capture_output=True, text=True)
        actual_result = result.stdout.strip().lower()

        LOGGER.info(
            f"Verifying {UNPRIVILEGED_USER} {'with admin rights can' if expected_result == 'yes' else 'can not'}"
            f" {verb} {resource}"
        )
        assert actual_result == expected_result, (
            f"Permission check failed for {UNPRIVILEGED_USER} to {verb} {resource}: "
            f"expected '{expected_result}', got '{actual_result}'"
        )


@pytest.fixture()
def namespace_admin_role_binding(admin_client, namespace):
    with RoleBinding(
        name=f"{UNPRIVILEGED_USER}-admin",
        namespace=namespace.name,
        client=admin_client,
        subjects_kind="User",
        subjects_name=UNPRIVILEGED_USER,
        role_ref_kind="ClusterRole",
        role_ref_name="admin",
    ) as role_binding:
        LOGGER.info(f"Granted admin role to {UNPRIVILEGED_USER} in namespace {namespace.name}")
        yield role_binding


@pytest.mark.parametrize(
    "namespace, expected_result",
    [
        pytest.param(
            {"use_unprivileged_client": False},
            "no",
        )
    ],
    indirect=["namespace"],
)
class TestUnprivilegedUserWithoutPermissions:
    """Test that users without admin rights cannot perform operations on OCP-V resources."""

    @pytest.mark.parametrize(
        "resource",
        [
            pytest.param(
                "virtualmachineinstances",
                marks=pytest.mark.polarion("CNV-12524"),
                id="vmi",
            ),
            pytest.param(
                "virtualmachines",
                marks=pytest.mark.polarion("CNV-2915"),
                id="vm",
            ),
            pytest.param(
                "virtualmachinepools",
                marks=pytest.mark.polarion("CNV-12525"),
                id="vmpool",
            ),
            pytest.param(
                "virtualmachineinstancepresets",
                marks=pytest.mark.polarion("CNV-2917"),
                id="vmi-preset",
            ),
            pytest.param(
                "virtualmachineinstancereplicasets",
                marks=pytest.mark.polarion("CNV-12523"),
                id="vmi-replica-set",
            ),
            pytest.param(
                "virtualmachineinstancemigrations",
                marks=pytest.mark.polarion("CNV-3235"),
                id="vmi-migration",
            ),
            pytest.param(
                "virtualmachinesnapshots",
                marks=pytest.mark.polarion("CNV-5246"),
                id="vm-snapshot",
            ),
            pytest.param(
                "virtualmachinesnapshotcontents",
                marks=pytest.mark.polarion("CNV-5247"),
                id="vm-snapshot-content",
            ),
            pytest.param(
                "virtualmachinerestores",
                marks=pytest.mark.polarion("CNV-5248"),
                id="vm-restore",
            ),
        ],
        indirect=False,
    )
    def test_unprivileged_user_permissions(self, resource, expected_result, namespace):
        """Verify unprivileged user has no permissions on OCP-V resources."""
        verify_permissions(
            resource=resource,
            expected_result=expected_result,
            namespace=namespace,
        )

    @pytest.mark.parametrize(
        "subresource, verb",
        [
            pytest.param(
                "virtualmachineinstances/pause",
                "update",
                marks=pytest.mark.polarion("CNV-12529"),
                id="vmi-pause",
            ),
            pytest.param(
                "virtualmachineinstances/unpause",
                "update",
                marks=pytest.mark.polarion("CNV-12528"),
                id="vmi-unpause",
            ),
            pytest.param(
                "virtualmachineinstances/softreboot",
                "update",
                marks=pytest.mark.polarion("CNV-12530"),
                id="vmi-softreboot",
            ),
            pytest.param(
                "virtualmachineinstances/console",
                "get",
                marks=pytest.mark.polarion("CNV-12536"),
                id="vmi-console",
            ),
            pytest.param(
                "virtualmachineinstances/vnc",
                "get",
                marks=pytest.mark.polarion("CNV-12537"),
                id="vmi-vnc",
            ),
            pytest.param(
                "virtualmachineinstances/vnc/screenshot",
                "get",
                marks=pytest.mark.polarion("CNV-12538"),
                id="vmi-vnc-screenshot",
            ),
            pytest.param(
                "virtualmachineinstances/guestosinfo",
                "get",
                marks=pytest.mark.polarion("CNV-12539"),
                id="vmi-guestosinfo",
            ),
        ],
        indirect=False,
    )
    def test_unprivileged_user_vmi_subresource_permissions(self, subresource, verb, expected_result, namespace):
        """Verify unprivileged user has no permissions on VMI subresources."""
        verify_permissions(
            resource=subresource,
            expected_result=expected_result,
            namespace=namespace,
            verbs=verb,
        )


@pytest.mark.parametrize(
    "expected_result",
    [
        pytest.param(
            "yes",
        )
    ],
    indirect=False,
)
@pytest.mark.usefixtures("namespace_admin_role_binding", "unprivileged_user_migrate_rolebinding")
class TestNamespaceAdminUser:
    @pytest.mark.parametrize(
        "resource",
        [
            pytest.param("virtualmachineinstances", marks=pytest.mark.polarion("CNV-2920"), id="vmi"),
            pytest.param("virtualmachines", marks=pytest.mark.polarion("CNV-2831"), id="vm"),
            pytest.param("virtualmachinepools", marks=pytest.mark.polarion("CNV-12522"), id="vmpool"),
            pytest.param("virtualmachineinstancepresets", marks=pytest.mark.polarion("CNV-2916"), id="vmi-preset"),
            pytest.param(
                "virtualmachineinstancereplicasets", marks=pytest.mark.polarion("CNV-2918"), id="vmi-replica-set"
            ),
            pytest.param(
                "virtualmachineinstancemigrations", marks=pytest.mark.polarion("CNV-2837"), id="vmi-migration"
            ),
            pytest.param("virtualmachinesnapshots", marks=pytest.mark.polarion("CNV-5249"), id="vm-snapshot"),
            pytest.param(
                "virtualmachinesnapshotcontents",
                marks=pytest.mark.polarion("CNV-5250"),
                id="vm-snapshot-content",
            ),
            pytest.param("virtualmachinerestores", marks=pytest.mark.polarion("CNV-5251"), id="vm-restore"),
        ],
        indirect=False,
    )
    def test_namespace_admin_permissions(self, resource, expected_result, namespace):
        """Verify namespace admin has full permissions on OCP-V resources."""
        verify_permissions(
            resource=resource,
            expected_result=expected_result,
            namespace=namespace,
        )

    @pytest.mark.parametrize(
        "subresource, verb",
        [
            pytest.param(
                "virtualmachineinstances/pause", "update", marks=pytest.mark.polarion("CNV-12526"), id="vmi-pause"
            ),
            pytest.param(
                "virtualmachineinstances/unpause", "update", marks=pytest.mark.polarion("CNV-12527"), id="vmi-unpause"
            ),
            pytest.param(
                "virtualmachineinstances/softreboot",
                "update",
                marks=pytest.mark.polarion("CNV-12531"),
                id="vmi-softreboot",
            ),
            pytest.param(
                "virtualmachineinstances/console", "get", marks=pytest.mark.polarion("CNV-12532"), id="vmi-console"
            ),
            pytest.param("virtualmachineinstances/vnc", "get", marks=pytest.mark.polarion("CNV-12533"), id="vmi-vnc"),
            pytest.param(
                "virtualmachineinstances/vnc/screenshot",
                "get",
                marks=pytest.mark.polarion("CNV-12534"),
                id="vmi-vnc-screenshot",
            ),
            pytest.param(
                "virtualmachineinstances/guestosinfo",
                "get",
                marks=pytest.mark.polarion("CNV-12535"),
                id="vmi-guestosinfo",
            ),
        ],
        indirect=False,
    )
    def test_namespace_admin_vmi_subresource_permissions(self, subresource, verb, expected_result, namespace):
        """Verify namespace admin has full permissions on VMI subresources."""
        verify_permissions(
            resource=subresource,
            expected_result=expected_result,
            namespace=namespace,
            verbs=verb,
        )
