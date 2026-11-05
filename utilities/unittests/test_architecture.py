# Generated using Claude cli

"""Unit tests for architecture module"""

import os
from unittest.mock import MagicMock, patch

import pytest

from utilities.architecture import get_cluster_architecture, get_multiarch_cpu_arch, get_worker_arch_pairs
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

    def test_get_cluster_architecture_from_env_multiarch(self):
        """Test getting architecture from environment variable - comma-separated multiarch"""
        with patch.dict(in_dict=os.environ, values={"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "amd64,arm64"}):
            result = get_cluster_architecture()
            assert result == {"amd64", "arm64"}

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

    @pytest.mark.parametrize("exit_flag", ["--help", "-h", "--version"])
    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_get_cluster_architecture_skips_cluster_on_exit_flag(self, mock_node_class, mock_cache_client, exit_flag):
        """Test that pytest exit flags skip cluster connection and return default architecture"""
        with patch.dict(in_dict=os.environ, values={}, clear=True), patch("utilities.architecture.sys") as mock_sys:
            mock_sys.argv = ["pytest", exit_flag]
            result = get_cluster_architecture()
            assert result == {"amd64"}
            mock_cache_client.assert_not_called()
            mock_node_class.get.assert_not_called()


class TestGetMultiarchCpuArch:
    @patch.dict("utilities.architecture.py_config", {"cpu_arch": "arm64", "cluster_type": "multiarch"})
    def test_returns_arch_on_multiarch_cluster_with_single_arch(self):
        assert get_multiarch_cpu_arch() == "arm64"

    @patch.dict("utilities.architecture.py_config", {"cpu_arch": "arm64", "cluster_type": "standard"})
    def test_returns_none_on_non_multiarch_cluster(self):
        assert get_multiarch_cpu_arch() is None

    @patch.dict("utilities.architecture.py_config", {"cluster_type": "multiarch"})
    def test_returns_none_when_cpu_arch_not_set(self):
        assert get_multiarch_cpu_arch() is None

    @patch.dict("utilities.architecture.py_config", {})
    def test_returns_none_when_no_config(self):
        assert get_multiarch_cpu_arch() is None


class TestGetWorkerArchPairs:
    """Test cases for get_worker_arch_pairs function."""

    def setup_method(self):
        """Clear cache before each test so env/node patches take effect."""
        get_worker_arch_pairs.cache_clear()

    # ------------------------------------------------------------------
    # env-var fast path
    # ------------------------------------------------------------------

    def test_single_arch_env_returns_no_pairs(self):
        """A single-arch env value produces an empty list (no pairs possible)."""
        with patch.dict(in_dict=os.environ, values={"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "amd64"}):
            assert get_worker_arch_pairs() == []

    def test_two_arch_env_returns_one_pair(self):
        """Two architectures in env produce exactly one sorted pair."""
        with patch.dict(in_dict=os.environ, values={"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "arm64,amd64"}):
            assert get_worker_arch_pairs() == [("amd64", "arm64")]

    def test_three_arch_env_returns_three_pairs(self):
        """Three architectures produce three sorted pairs."""
        with patch.dict(in_dict=os.environ, values={"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "amd64,arm64,s390x"}):
            assert get_worker_arch_pairs() == [("amd64", "arm64"), ("amd64", "s390x"), ("arm64", "s390x")]

    def test_env_pairs_are_sorted(self):
        """Pairs are returned in sorted order regardless of env var order."""
        with patch.dict(in_dict=os.environ, values={"OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH": "s390x,amd64"}):
            result = get_worker_arch_pairs()
            assert result == [("amd64", "s390x")]
            assert result[0][0] < result[0][1]

    # ------------------------------------------------------------------
    # node-API path
    # ------------------------------------------------------------------

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_non_worker_nodes_are_excluded(self, mock_node_class, mock_cache_client):
        """Control-plane nodes (no worker label) are not counted."""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            master_node = MagicMock()
            master_node.labels = {"kubernetes.io/arch": "amd64"}  # no worker label
            worker_node = MagicMock()
            worker_node.labels = {
                "kubernetes.io/arch": "arm64",
                "node-role.kubernetes.io/worker": "",
            }
            mock_node_class.get.return_value = [master_node, worker_node]
            mock_cache_client.return_value = MagicMock()

            # Only one worker arch → no pairs
            assert get_worker_arch_pairs() == []

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_two_worker_archs_returns_one_pair(self, mock_node_class, mock_cache_client):
        """Two distinct worker architectures yield one pair."""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            worker_label = "node-role.kubernetes.io/worker"
            node_amd = MagicMock()
            node_amd.labels = {"kubernetes.io/arch": "amd64", worker_label: ""}
            node_arm = MagicMock()
            node_arm.labels = {"kubernetes.io/arch": "arm64", worker_label: ""}
            mock_node_class.get.return_value = [node_amd, node_arm]
            mock_cache_client.return_value = MagicMock()

            assert get_worker_arch_pairs() == [("amd64", "arm64")]

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_duplicate_worker_nodes_same_arch_count_once(self, mock_node_class, mock_cache_client):
        """Multiple workers of the same arch are deduplicated before pairing."""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            worker_label = "node-role.kubernetes.io/worker"
            node1 = MagicMock()
            node1.labels = {"kubernetes.io/arch": "arm64", worker_label: ""}
            node2 = MagicMock()
            node2.labels = {"kubernetes.io/arch": "arm64", worker_label: ""}
            node3 = MagicMock()
            node3.labels = {"kubernetes.io/arch": "s390x", worker_label: ""}
            mock_node_class.get.return_value = [node1, node2, node3]
            mock_cache_client.return_value = MagicMock()

            assert get_worker_arch_pairs() == [("arm64", "s390x")]

    @patch("utilities.architecture.cache_admin_client")
    @patch("utilities.architecture.Node")
    def test_result_is_cached(self, mock_node_class, mock_cache_client):
        """Node.get() is called only once across multiple invocations."""
        with patch.dict(in_dict=os.environ, values={}, clear=True):
            worker_label = "node-role.kubernetes.io/worker"
            node = MagicMock()
            node.labels = {"kubernetes.io/arch": "amd64", worker_label: ""}
            mock_node_class.get.return_value = [node]
            mock_cache_client.return_value = MagicMock()

            get_worker_arch_pairs()
            get_worker_arch_pairs()

            mock_node_class.get.assert_called_once()
