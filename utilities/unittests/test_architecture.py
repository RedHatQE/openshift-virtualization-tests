# Generated using Claude cli

"""Unit tests for architecture module"""

import os
from unittest.mock import MagicMock, patch

import pytest

from utilities.architecture import get_cluster_architecture
from utilities.exceptions import UnsupportedCPUArchitectureError


class TestGetClusterArchitecture:
    """Test cases for get_cluster_architecture function"""

    def setup_method(self):
        """Clear cache before each test so env/node patches take effect"""
        get_cluster_architecture.cache_clear()

    def test_get_cluster_architecture_from_env_arm64(self):
        """Test getting architecture from environment variable - arm64"""
        with patch.dict(in_dict=os.environ, values={"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "arm64"}):
            result = get_cluster_architecture()
            assert result == {"arm64"}

    def test_get_cluster_architecture_from_env_s390x(self):
        """Test getting architecture from environment variable - s390x"""
        with patch.dict(in_dict=os.environ, values={"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "s390x"}):
            result = get_cluster_architecture()
            assert result == {"s390x"}

    def test_get_cluster_architecture_from_env_amd64(self):
        """Test getting architecture from environment variable - amd64"""
        with patch.dict(in_dict=os.environ, values={"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "amd64"}):
            result = get_cluster_architecture()
            assert result == {"amd64"}

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_from_nodes_amd64(self, mock_node_class, mock_cache_client):
        """Test getting architecture from nodes - amd64"""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            # Mock node with amd64 architecture
            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "amd64"}
            mock_node_class.get.return_value = [mock_node]
            mock_cache_client.return_value = MagicMock()

            result = get_cluster_architecture()

            assert result == {"amd64"}
            mock_node_class.get.assert_called_once()
            mock_cache_client.assert_called_once()

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_from_nodes_arm64(self, mock_node_class, mock_cache_client):
        """Test getting architecture from nodes - arm64"""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            # Mock node with arm64 architecture
            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "arm64"}
            mock_node_class.get.return_value = [mock_node]
            mock_cache_client.return_value = MagicMock()

            result = get_cluster_architecture()

            assert result == {"arm64"}

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_from_nodes_s390x(self, mock_node_class, mock_cache_client):
        """Test getting architecture from nodes - s390x"""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            # Mock node with s390x architecture
            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "s390x"}
            mock_node_class.get.return_value = [mock_node]
            mock_cache_client.return_value = MagicMock()

            result = get_cluster_architecture()

            assert result == {"s390x"}

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_multiple_nodes_same_arch(self, mock_node_class, mock_cache_client):
        """Test getting architecture with multiple nodes of same arch returns set"""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            # Mock multiple nodes with same architecture
            mock_node1 = MagicMock()
            mock_node1.labels = {"kubernetes.io/arch": "amd64"}
            mock_node2 = MagicMock()
            mock_node2.labels = {"kubernetes.io/arch": "amd64"}
            mock_node_class.get.return_value = [mock_node1, mock_node2]
            mock_cache_client.return_value = MagicMock()

            result = get_cluster_architecture()

            assert result == {"amd64"}

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_multiple_archs_returns_set(self, mock_node_class, mock_cache_client):
        """Test getting architecture with mixed nodes returns set of all archs"""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            mock_node1 = MagicMock()
            mock_node1.labels = {"kubernetes.io/arch": "amd64"}
            mock_node2 = MagicMock()
            mock_node2.labels = {"kubernetes.io/arch": "arm64"}
            mock_node_class.get.return_value = [mock_node1, mock_node2]
            mock_cache_client.return_value = MagicMock()

            result = get_cluster_architecture()

            assert result == {"amd64", "arm64"}

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_uses_cache_admin_client(self, mock_node_class, mock_cache_client):
        """Test that cache_admin_client is used when getting nodes"""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            mock_client = MagicMock()
            mock_cache_client.return_value = mock_client

            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "amd64"}
            mock_node_class.get.return_value = [mock_node]

            get_cluster_architecture()

            # Verify cache_admin_client was called and passed to Node.get
            mock_cache_client.assert_called_once()
            mock_node_class.get.assert_called_once_with(client=mock_client)

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_raises_error_when_no_nodes(self, mock_node_class, mock_cache_client):
        """Test that UnsupportedCPUArchitectureError is raised when no nodes are found"""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            mock_cache_client.return_value = MagicMock()
            mock_node_class.get.return_value = []

            with pytest.raises(
                UnsupportedCPUArchitectureError,
                match="Cluster architecture could not be determined",
            ):
                get_cluster_architecture()
