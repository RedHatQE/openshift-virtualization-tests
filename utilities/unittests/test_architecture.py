# Generated using Claude cli

"""Unit tests for architecture module"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from architecture import get_cluster_architecture


class TestGetClusterArchitecture:
    """Test cases for get_cluster_architecture function"""

    def test_get_cluster_architecture_from_env(self):
        """Test getting architecture from environment variable"""
        with patch.dict(os.environ, {"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "arm64"}):
            result = get_cluster_architecture()
            assert result == "arm64"

    @patch("architecture.Node")
    @patch("architecture.get_client")
    def test_get_cluster_architecture_from_nodes_x86_64(self, mock_get_client, mock_node_class):
        """Test getting architecture from nodes - x86_64"""
        # Clear env var to force reading from nodes
        with patch.dict(os.environ, {}, clear=True):
            # Mock node with x86_64 architecture
            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "amd64"}
            mock_node_class.get.return_value = [mock_node]

            result = get_cluster_architecture()

            # Should convert amd64 to x86_64
            assert result == "x86_64"
            mock_node_class.get.assert_called_once()

    @patch("architecture.Node")
    @patch("architecture.get_client")
    def test_get_cluster_architecture_from_nodes_arm64(self, mock_get_client, mock_node_class):
        """Test getting architecture from nodes - arm64"""
        with patch.dict(os.environ, {}, clear=True):
            # Mock node with arm64 architecture
            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "arm64"}
            mock_node_class.get.return_value = [mock_node]

            result = get_cluster_architecture()

            assert result == "arm64"

    @patch("architecture.Node")
    @patch("architecture.get_client")
    def test_get_cluster_architecture_from_nodes_s390x(self, mock_get_client, mock_node_class):
        """Test getting architecture from nodes - s390x"""
        with patch.dict(os.environ, {}, clear=True):
            # Mock node with s390x architecture
            mock_node = MagicMock()
            mock_node.labels = {"kubernetes.io/arch": "s390x"}
            mock_node_class.get.return_value = [mock_node]

            result = get_cluster_architecture()

            assert result == "s390x"

    @patch("architecture.Node")
    @patch("architecture.get_client")
    def test_get_cluster_architecture_unsupported(self, mock_get_client, mock_node_class):
        """Test unsupported architecture raises ValueError"""
        with (
            patch.dict(os.environ, {"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "unsupported"}),
            pytest.raises(
                ValueError,
                match="unsupported architecture in not supported",
            ),
        ):
            get_cluster_architecture()

    @patch("architecture.Node")
    @patch("architecture.get_client")
    def test_get_cluster_architecture_multiple_nodes(self, mock_get_client, mock_node_class):
        """Test getting architecture with multiple nodes of same arch"""
        with patch.dict(os.environ, {}, clear=True):
            # Mock multiple nodes with same architecture
            mock_node1 = MagicMock()
            mock_node1.labels = {"kubernetes.io/arch": "amd64"}
            mock_node2 = MagicMock()
            mock_node2.labels = {"kubernetes.io/arch": "amd64"}
            mock_node_class.get.return_value = [mock_node1, mock_node2]

            result = get_cluster_architecture()

            assert result == "x86_64"
