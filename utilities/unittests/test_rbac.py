"""Unit tests for rbac module"""

from unittest.mock import MagicMock, patch

from utilities.rbac import set_permissions


@patch("utilities.rbac.RoleBinding")
@patch("utilities.rbac.ClusterRole")
def test_set_permissions_binds_created_cluster_role(mock_cluster_role_class, mock_role_binding_class):
    # set_permissions calls create_cluster_role and create_role_binding, so this
    # single test covers all three helpers in the module.
    mock_cluster_role = MagicMock(kind="ClusterRole")
    mock_cluster_role.name = "test-role"
    mock_cluster_role.__enter__ = MagicMock(return_value=mock_cluster_role)
    mock_cluster_role.__exit__ = MagicMock(return_value=False)
    mock_cluster_role_class.return_value = mock_cluster_role

    mock_role_binding = MagicMock()
    mock_role_binding.__enter__ = MagicMock(return_value=mock_role_binding)
    mock_role_binding.__exit__ = MagicMock(return_value=False)
    mock_role_binding_class.return_value = mock_role_binding

    with set_permissions(
        client=MagicMock(),
        role_name="test-role",
        role_api_groups=["kubevirt.io"],
        verbs=["create"],
        permissions_to_resources=["virtualmachines"],
        binding_name="test-binding",
        namespace="test-namespace",
        subjects_name="unprivileged-user",
    ):
        pass

    role_binding_kwargs = mock_role_binding_class.call_args[1]
    assert role_binding_kwargs["role_ref_kind"] == mock_cluster_role.kind
    assert role_binding_kwargs["role_ref_name"] == mock_cluster_role.name
