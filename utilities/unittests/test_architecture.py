# Generated using Claude cli

"""Unit tests for architecture module"""

import os
from unittest.mock import MagicMock, patch

import pytest

from utilities.architecture import get_cluster_architecture


class TestGetClusterArchitecture:
    """Test cases for get_cluster_architecture function"""

    def test_get_cluster_architecture_from_env_arm64(self):
        """Test getting architecture from environment variable - arm64"""
        with patch.dict(os.environ, {"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "arm64"}):
            result = get_cluster_architecture()
            assert result == "arm64"

    def test_get_cluster_architecture_from_env_x86_64(self):
        """Test getting architecture from environment variable - x86_64"""
        with patch.dict(os.environ, {"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "x86_64"}):
            result = get_cluster_architecture()
            assert result == "x86_64"

    def test_get_cluster_architecture_from_env_s390x(self):
        """Test getting architecture from environment variable - s390x"""
        with patch.dict(os.environ, {"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "s390x"}):
            result = get_cluster_architecture()
            assert result == "s390x"

    def test_get_cluster_architecture_from_env_amd64_converts_to_x86_64(self):
        """Test that amd64 from env is converted to x86_64"""
        with patch.dict(os.environ, {"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "amd64"}):
            result = get_cluster_architecture()
            assert result == "x86_64"

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_from_nodes_x86_64(self, mock_node_class, mock_cache_client):
        """Test getting architecture from nodes - x86_64"""
        # Clear env var to force reading from nodes
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH", None)

            # Mock node with amd64 architecture
            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "amd64"}
            mock_node_class.get.return_value = [mock_node]
            mock_cache_client.return_value = MagicMock()

            result = get_cluster_architecture()

            # Should convert amd64 to x86_64
            assert result == "x86_64"
            mock_node_class.get.assert_called_once()
            mock_cache_client.assert_called_once()

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_from_nodes_arm64(self, mock_node_class, mock_cache_client):
        """Test getting architecture from nodes - arm64"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH", None)

            # Mock node with arm64 architecture
            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "arm64"}
            mock_node_class.get.return_value = [mock_node]
            mock_cache_client.return_value = MagicMock()

            result = get_cluster_architecture()

            assert result == "arm64"

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_from_nodes_s390x(self, mock_node_class, mock_cache_client):
        """Test getting architecture from nodes - s390x"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH", None)

            # Mock node with s390x architecture
            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "s390x"}
            mock_node_class.get.return_value = [mock_node]
            mock_cache_client.return_value = MagicMock()

            result = get_cluster_architecture()

            assert result == "s390x"

    def test_get_cluster_architecture_unsupported(self):
        """Test unsupported architecture raises ValueError"""
        with (
            patch.dict(os.environ, {"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "unsupported"}),
            pytest.raises(
                ValueError,
                match="unsupported architecture in not supported",
            ),
        ):
            get_cluster_architecture()

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_multiple_nodes(self, mock_node_class, mock_cache_client):
        """Test getting architecture with multiple nodes of same arch"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH", None)

            # Mock multiple nodes with same architecture
            mock_node1 = MagicMock()
            mock_node1.labels = {"kubernetes.io/arch": "amd64"}
            mock_node2 = MagicMock()
            mock_node2.labels = {"kubernetes.io/arch": "amd64"}
            mock_node_class.get.return_value = [mock_node1, mock_node2]
            mock_cache_client.return_value = MagicMock()

            result = get_cluster_architecture()

            assert result == "x86_64"

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_uses_cache_admin_client(self, mock_node_class, mock_cache_client):
        """Test that cache_admin_client is used when getting nodes"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH", None)

            mock_client = MagicMock()
            mock_cache_client.return_value = mock_client

            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "amd64"}
            mock_node_class.get.return_value = [mock_node]

            get_cluster_architecture()

            # Verify cache_admin_client was called and passed to Node.get
            mock_cache_client.assert_called_once()
            mock_node_class.get.assert_called_once_with(client=mock_client)
