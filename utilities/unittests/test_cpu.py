# Generated using Claude cli

"""Unit tests for cpu module"""

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utilities.cpu import (
    find_common_cpu_model_for_live_migration,
    get_common_cpu_from_nodes,
    get_host_model_cpu,
    get_nodes_cpu_model,
    is_cpu_model_not_in_excluded_list,
)


class TestGetNodesCpuModel:
    """Test cases for get_nodes_cpu_model function"""

    def test_get_nodes_cpu_model_with_valid_labels(self):
        """Test with nodes having CPU model labels"""
        mock_node1 = MagicMock()
        mock_node1.name = "node1"
        mock_node1.labels = {
            "cpu-model.node.kubevirt.io/Skylake-Server": "true",
            "cpu-model.node.kubevirt.io/Cascadelake": "true",
            "cpu-model.node.kubevirt.io/Opteron": "true",  # Should be excluded
        }

        mock_node2 = MagicMock()
        mock_node2.name = "node2"
        mock_node2.labels = {
            "cpu-model.node.kubevirt.io/Haswell": "true",
            "cpu-model.node.kubevirt.io/Penryn": "true",  # Should be excluded
        }

        nodes = [mock_node1, mock_node2]
        result = get_nodes_cpu_model(nodes)

        # Verify structure
        assert "common" in result
        assert "modern" in result

        # Verify node1: Cascadelake should be in both, Skylake-Server in common only, Opteron excluded
        assert "Cascadelake" in result["common"]["node1"]
        assert "Skylake-Server" in result["common"]["node1"]
        assert "Opteron" not in result["common"]["node1"]
        assert "Cascadelake" in result["modern"]["node1"]
        # Skylake is in EXCLUDED_OLD_CPU_MODELS, should not be in modern
        assert "Skylake-Server" not in result["modern"]["node1"]

        # Verify node2: Haswell should be in both, Penryn excluded
        assert "Haswell" in result["common"]["node2"]
        assert "Penryn" not in result["common"]["node2"]
        assert "Haswell" in result["modern"]["node2"]

    def test_get_nodes_cpu_model_both_common_and_modern(self):
        """Test with nodes having both common and modern CPUs"""
        mock_node = MagicMock()
        mock_node.name = "node1"
        mock_node.labels = {
            "cpu-model.node.kubevirt.io/Cascadelake": "true",  # Modern
            "cpu-model.node.kubevirt.io/Westmere": "true",  # Old (excluded from modern)
            "cpu-model.node.kubevirt.io/Opteron": "true",  # Excluded from both
        }

        result = get_nodes_cpu_model([mock_node])

        # Cascadelake should be in both
        assert "Cascadelake" in result["common"]["node1"]
        assert "Cascadelake" in result["modern"]["node1"]

        # Westmere should be in common but not modern
        assert "Westmere" in result["common"]["node1"]
        assert "Westmere" not in result["modern"]["node1"]

        # Opteron should be excluded from both
        assert "Opteron" not in result["common"]["node1"]
        assert "Opteron" not in result["modern"]["node1"]

    def test_get_nodes_cpu_model_excluded_models_filtered(self):
        """Test with excluded CPU models filtered out"""
        mock_node = MagicMock()
        mock_node.name = "node1"
        mock_node.labels = {
            "cpu-model.node.kubevirt.io/Opteron_G1": "true",  # Contains Opteron
            "cpu-model.node.kubevirt.io/Penryn": "true",  # Exact match
            "cpu-model.node.kubevirt.io/Cascadelake": "true",  # Valid
        }

        result = get_nodes_cpu_model([mock_node])

        # Opteron and Penryn should be excluded
        assert "Opteron_G1" not in result["common"]["node1"]
        assert "Penryn" not in result["common"]["node1"]

        # Cascadelake should be included
        assert "Cascadelake" in result["common"]["node1"]

    def test_get_nodes_cpu_model_excluded_old_models_filtered(self):
        """Test with excluded old CPU models filtered out"""
        mock_node = MagicMock()
        mock_node.name = "node1"
        mock_node.labels = {
            "cpu-model.node.kubevirt.io/Westmere": "true",
            "cpu-model.node.kubevirt.io/SandyBridge": "true",
            "cpu-model.node.kubevirt.io/Nehalem": "true",
            "cpu-model.node.kubevirt.io/IvyBridge": "true",
            "cpu-model.node.kubevirt.io/Skylake-Client": "true",
            "cpu-model.node.kubevirt.io/Cascadelake": "true",
        }

        result = get_nodes_cpu_model([mock_node])

        # All old models should be in common
        assert "Westmere" in result["common"]["node1"]
        assert "SandyBridge" in result["common"]["node1"]
        assert "Nehalem" in result["common"]["node1"]
        assert "IvyBridge" in result["common"]["node1"]
        assert "Skylake-Client" in result["common"]["node1"]

        # Old models should NOT be in modern
        assert "Westmere" not in result["modern"]["node1"]
        assert "SandyBridge" not in result["modern"]["node1"]
        assert "Nehalem" not in result["modern"]["node1"]
        assert "IvyBridge" not in result["modern"]["node1"]
        assert "Skylake-Client" not in result["modern"]["node1"]

        # Modern model should be in both
        assert "Cascadelake" in result["common"]["node1"]
        assert "Cascadelake" in result["modern"]["node1"]

    def test_get_nodes_cpu_model_empty_nodes_list(self):
        """Test with empty nodes list"""
        result = get_nodes_cpu_model([])

        assert result == {"common": {}, "modern": {}}

    def test_get_nodes_cpu_model_no_cpu_labels(self):
        """Test with nodes having no CPU labels"""
        mock_node = MagicMock()
        mock_node.name = "node1"
        mock_node.labels = {
            "kubernetes.io/arch": "amd64",
            "kubernetes.io/os": "linux",
        }

        result = get_nodes_cpu_model([mock_node])

        assert result["common"]["node1"] == set()
        assert result["modern"]["node1"] == set()


class TestIsCpuModelNotInExcludedList:
    """Test cases for is_cpu_model_not_in_excluded_list function"""

    def test_returns_true_when_valid(self):
        """Test returns True when match exists, value is 'true', CPU not in filter list"""
        filter_list = ["Opteron", "Penryn"]
        match = re.match(r"cpu-model\.node\.kubevirt\.io/(.*)", "cpu-model.node.kubevirt.io/Cascadelake")
        label_value = "true"

        result = is_cpu_model_not_in_excluded_list(filter_list, match, label_value)

        assert result is True

    def test_returns_false_when_match_is_none(self):
        """Test returns False when match is None"""
        filter_list = ["Opteron", "Penryn"]
        match = None
        label_value = "true"

        result = is_cpu_model_not_in_excluded_list(filter_list, match, label_value)

        assert result is False

    def test_returns_false_when_label_value_not_true(self):
        """Test returns False when label_value is not 'true'"""
        filter_list = ["Opteron", "Penryn"]
        match = re.match(r"cpu-model\.node\.kubevirt\.io/(.*)", "cpu-model.node.kubevirt.io/Cascadelake")
        label_value = "false"

        result = is_cpu_model_not_in_excluded_list(filter_list, match, label_value)

        assert result is False

    def test_returns_false_when_cpu_in_filter_list(self):
        """Test returns False when CPU is in filter list"""
        filter_list = ["Opteron", "Penryn"]
        match = re.match(r"cpu-model\.node\.kubevirt\.io/(.*)", "cpu-model.node.kubevirt.io/Opteron_G1")
        label_value = "true"

        result = is_cpu_model_not_in_excluded_list(filter_list, match, label_value)

        assert result is False

    def test_returns_false_when_cpu_contains_filter_element(self):
        """Test returns False when CPU name contains any filter element"""
        filter_list = ["Opteron", "Penryn"]
        match = re.match(r"cpu-model\.node\.kubevirt\.io/(.*)", "cpu-model.node.kubevirt.io/Penryn-v2")
        label_value = "true"

        result = is_cpu_model_not_in_excluded_list(filter_list, match, label_value)

        assert result is False


class TestGetHostModelCpu:
    """Test cases for get_host_model_cpu function"""

    @patch("utilities.cpu.py_config", {"cpu_arch": "amd64"})
    def test_successful_extraction_all_nodes(self):
        """Test successful extraction of host model CPU from all nodes (filtered by cpu_arch)"""
        mock_node1 = MagicMock()
        mock_node1.name = "node1"
        mock_node1.labels = {
            "host-model-cpu.node.kubevirt.io/Cascadelake-Server": "true",
            "kubernetes.io/arch": "amd64",
        }

        mock_node2 = MagicMock()
        mock_node2.name = "node2"
        mock_node2.labels = {
            "host-model-cpu.node.kubevirt.io/Skylake-Server": "true",
            "kubernetes.io/arch": "amd64",
        }

        result = get_host_model_cpu([mock_node1, mock_node2])

        assert result == {
            "node1": "Cascadelake-Server",
            "node2": "Skylake-Server",
        }

    @patch("utilities.cpu.py_config", {"cpu_arch": "amd64"})
    def test_assertion_error_when_missing_label(self):
        """Test assertion error when not all nodes have host-model-cpu label"""
        mock_node1 = MagicMock()
        mock_node1.name = "node1"
        mock_node1.labels = {
            "host-model-cpu.node.kubevirt.io/Cascadelake-Server": "true",
            "kubernetes.io/arch": "amd64",
        }

        mock_node2 = MagicMock()
        mock_node2.name = "node2"
        mock_node2.labels = {
            "kubernetes.io/arch": "amd64",
        }

        with pytest.raises(AssertionError, match="All nodes did not have host-model-cpu label"):
            get_host_model_cpu([mock_node1, mock_node2])

    @patch("utilities.cpu.py_config", {"cpu_arch": "amd64"})
    def test_multiple_nodes_same_host_cpu(self):
        """Test with multiple nodes with same host CPU"""
        mock_node1 = MagicMock()
        mock_node1.name = "node1"
        mock_node1.labels = {
            "host-model-cpu.node.kubevirt.io/Cascadelake-Server": "true",
            "kubernetes.io/arch": "amd64",
        }

        mock_node2 = MagicMock()
        mock_node2.name = "node2"
        mock_node2.labels = {
            "host-model-cpu.node.kubevirt.io/Cascadelake-Server": "true",
            "kubernetes.io/arch": "amd64",
        }

        result = get_host_model_cpu([mock_node1, mock_node2])

        assert result == {
            "node1": "Cascadelake-Server",
            "node2": "Cascadelake-Server",
        }

    @patch("utilities.cpu.py_config", {"cpu_arch": "amd64"})
    def test_multiple_nodes_different_host_cpus(self):
        """Test with multiple nodes with different host CPUs"""
        mock_node1 = MagicMock()
        mock_node1.name = "node1"
        mock_node1.labels = {
            "host-model-cpu.node.kubevirt.io/Cascadelake-Server": "true",
            "kubernetes.io/arch": "amd64",
        }

        mock_node2 = MagicMock()
        mock_node2.name = "node2"
        mock_node2.labels = {
            "host-model-cpu.node.kubevirt.io/Skylake-Server": "true",
            "kubernetes.io/arch": "amd64",
        }

        mock_node3 = MagicMock()
        mock_node3.name = "node3"
        mock_node3.labels = {
            "host-model-cpu.node.kubevirt.io/Haswell": "true",
            "kubernetes.io/arch": "amd64",
        }

        result = get_host_model_cpu([mock_node1, mock_node2, mock_node3])

        assert result == {
            "node1": "Cascadelake-Server",
            "node2": "Skylake-Server",
            "node3": "Haswell",
        }

    @patch("utilities.cpu.py_config", {"cpu_arch": "amd64"})
    def test_label_value_not_true_ignored(self):
        """Test that labels with value != 'true' are ignored"""
        mock_node1 = MagicMock()
        mock_node1.name = "node1"
        mock_node1.labels = {
            "host-model-cpu.node.kubevirt.io/Cascadelake-Server": "false",
            "kubernetes.io/arch": "amd64",
        }

        with pytest.raises(AssertionError, match="All nodes did not have host-model-cpu label"):
            get_host_model_cpu([mock_node1])

    @patch("utilities.cpu.py_config", {"cpu_arch": "amd64"})
    def test_filters_nodes_by_cpu_arch(self):
        """Test that nodes not matching cpu_arch are excluded from host model extraction"""
        mock_node_amd64 = MagicMock()
        mock_node_amd64.name = "node-amd64"
        mock_node_amd64.labels = {
            "host-model-cpu.node.kubevirt.io/Cascadelake-Server": "true",
            "kubernetes.io/arch": "amd64",
        }

        mock_node_arm64 = MagicMock()
        mock_node_arm64.name = "node-arm64"
        mock_node_arm64.labels = {
            "host-model-cpu.node.kubevirt.io/Neoverse-N1": "true",
            "kubernetes.io/arch": "arm64",
        }

        result = get_host_model_cpu([mock_node_amd64, mock_node_arm64])

        # Only amd64 node should be included
        assert result == {"node-amd64": "Cascadelake-Server"}


class TestFindCommonCpuModelForLiveMigration:
    """Test cases for find_common_cpu_model_for_live_migration function"""

    @patch("utilities.cpu.LOGGER")
    def test_returns_none_when_homogeneous(self, mock_logger):
        """Test returns None when all host CPUs are same (homogeneous)"""
        cluster_cpu = "Cascadelake-Server"
        host_cpu_model = {
            "node1": "Skylake-Server",
            "node2": "Skylake-Server",
            "node3": "Skylake-Server",
        }

        result = find_common_cpu_model_for_live_migration(cluster_cpu, host_cpu_model)

        assert result is None
        mock_logger.info.assert_called_once_with(
            f"Host model cpus for all nodes are same {host_cpu_model}. No common cpus are needed"
        )

    @patch("utilities.cpu.LOGGER")
    def test_returns_cluster_cpu_when_heterogeneous_with_common(self, mock_logger):
        """Test returns cluster_cpu when host CPUs differ (heterogeneous with common CPU)"""
        cluster_cpu = "Cascadelake-Server"
        host_cpu_model = {
            "node1": "Skylake-Server",
            "node2": "Cascadelake-Server",
            "node3": "Haswell",
        }

        result = find_common_cpu_model_for_live_migration(cluster_cpu, host_cpu_model)

        assert result == "Cascadelake-Server"
        mock_logger.info.assert_called_once_with(f"Using cluster node cpu: {cluster_cpu}")

    @patch("utilities.cpu.LOGGER")
    def test_returns_none_when_no_cluster_cpu_heterogeneous(self, mock_logger):
        """Test returns None when cluster_cpu is None/empty and heterogeneous"""
        cluster_cpu = None
        host_cpu_model = {
            "node1": "Skylake-Server",
            "node2": "Cascadelake-Server",
        }

        result = find_common_cpu_model_for_live_migration(cluster_cpu, host_cpu_model)

        assert result is None
        mock_logger.warning.assert_called_once_with("This is a heterogeneous cluster with no common cluster cpu.")

    @patch("utilities.cpu.LOGGER")
    def test_logging_for_homogeneous_cluster(self, mock_logger):
        """Test logging for homogeneous cluster scenario"""
        cluster_cpu = "SomeClusterCPU"
        host_cpu_model = {
            "node1": "IdenticalCPU",
            "node2": "IdenticalCPU",
        }

        find_common_cpu_model_for_live_migration(cluster_cpu, host_cpu_model)

        assert mock_logger.info.call_count == 1
        assert mock_logger.warning.call_count == 0

    @patch("utilities.cpu.LOGGER")
    def test_logging_for_heterogeneous_cluster_with_common_cpu(self, mock_logger):
        """Test logging for heterogeneous cluster with common CPU"""
        cluster_cpu = "CommonCPU"
        host_cpu_model = {
            "node1": "CPU1",
            "node2": "CPU2",
        }

        find_common_cpu_model_for_live_migration(cluster_cpu, host_cpu_model)

        assert mock_logger.info.call_count == 1
        assert mock_logger.warning.call_count == 0

    @patch("utilities.cpu.LOGGER")
    def test_logging_for_heterogeneous_cluster_no_common_cpu(self, mock_logger):
        """Test logging for heterogeneous cluster without common CPU"""
        cluster_cpu = None
        host_cpu_model = {
            "node1": "CPU1",
            "node2": "CPU2",
        }

        find_common_cpu_model_for_live_migration(cluster_cpu, host_cpu_model)

        assert mock_logger.info.call_count == 0
        assert mock_logger.warning.call_count == 1


class TestGetCommonCpuFromNodes:
    """Test cases for get_common_cpu_from_nodes function"""

    def test_returns_cpu_from_non_empty_set(self):
        """Test returns CPU from non-empty set"""
        cluster_cpus = {"Cascadelake-Server", "Skylake-Server", "Haswell"}

        result = get_common_cpu_from_nodes(cluster_cpus)

        assert result in cluster_cpus

    def test_returns_none_for_empty_set(self):
        """Test returns None for empty set"""
        cluster_cpus = set()

        result = get_common_cpu_from_nodes(cluster_cpus)

        assert result is None

    def test_returns_single_cpu_from_single_element_set(self):
        """Test returns single CPU from single element set"""
        cluster_cpus = {"Cascadelake-Server"}

        result = get_common_cpu_from_nodes(cluster_cpus)

        assert result == "Cascadelake-Server"
