# Generated using Claude cli

"""Unit tests for pytest_matrix_utils module"""

from unittest.mock import MagicMock, patch

from utilities.pytest_matrix_utils import (  # noqa: E402
    hpp_matrix,
    online_resize_matrix,
    snapshot_matrix,
    wffc_matrix,
    without_snapshot_capability_matrix,
)


class TestSnapshotMatrix:
    """Test cases for snapshot_matrix function"""

    def test_snapshot_matrix_with_snapshot_enabled(self):
        """Test snapshot_matrix filters storage classes with snapshot enabled"""
        matrix = [
            {"sc-with-snapshot": {"snapshot": True, "other": "value"}},
            {"sc-without-snapshot": {"snapshot": False, "other": "value"}},
            {"sc-with-snapshot-2": {"snapshot": True, "other": "value"}},
        ]

        result = snapshot_matrix(matrix)

        assert len(result) == 2
        assert {"sc-with-snapshot": {"snapshot": True, "other": "value"}} in result
        assert {"sc-with-snapshot-2": {"snapshot": True, "other": "value"}} in result
        assert {"sc-without-snapshot": {"snapshot": False, "other": "value"}} not in result

    def test_snapshot_matrix_empty_matrix(self):
        """Test snapshot_matrix with empty matrix"""
        matrix = []

        result = snapshot_matrix(matrix)

        assert result == []

    def test_snapshot_matrix_no_snapshot_enabled(self):
        """Test snapshot_matrix with no snapshot enabled storage classes"""
        matrix = [
            {"sc-without-snapshot-1": {"snapshot": False, "other": "value"}},
            {"sc-without-snapshot-2": {"snapshot": False, "other": "value"}},
        ]

        result = snapshot_matrix(matrix)

        assert result == []


class TestWithoutSnapshotCapabilityMatrix:
    """Test cases for without_snapshot_capability_matrix function"""

    def test_without_snapshot_capability_matrix(self):
        """Test without_snapshot_capability_matrix filters storage classes without snapshot capability"""
        matrix = [
            {"sc-with-snapshot": {"snapshot": True, "other": "value"}},
            {"sc-without-snapshot": {"snapshot": False, "other": "value"}},
            {"sc-without-snapshot-2": {"snapshot": False, "other": "value"}},
        ]

        result = without_snapshot_capability_matrix(matrix)

        assert len(result) == 2
        assert {"sc-without-snapshot": {"snapshot": False, "other": "value"}} in result
        assert {"sc-without-snapshot-2": {"snapshot": False, "other": "value"}} in result
        assert {"sc-with-snapshot": {"snapshot": True, "other": "value"}} not in result

    def test_without_snapshot_capability_matrix_empty_matrix(self):
        """Test without_snapshot_capability_matrix with empty matrix"""
        matrix = []

        result = without_snapshot_capability_matrix(matrix)

        assert result == []

    def test_without_snapshot_capability_matrix_all_have_snapshot(self):
        """Test without_snapshot_capability_matrix with all storage classes having snapshot capability"""
        matrix = [
            {"sc-with-snapshot-1": {"snapshot": True, "other": "value"}},
            {"sc-with-snapshot-2": {"snapshot": True, "other": "value"}},
        ]

        result = without_snapshot_capability_matrix(matrix)

        assert result == []


class TestOnlineResizeMatrix:
    """Test cases for online_resize_matrix function"""

    def test_online_resize_matrix_with_online_resize_enabled(self):
        """Test online_resize_matrix filters storage classes with online resize enabled"""
        matrix = [
            {"sc-with-resize": {"online_resize": True, "other": "value"}},
            {"sc-without-resize": {"online_resize": False, "other": "value"}},
            {"sc-with-resize-2": {"online_resize": True, "other": "value"}},
        ]

        result = online_resize_matrix(matrix)

        assert len(result) == 2
        assert {"sc-with-resize": {"online_resize": True, "other": "value"}} in result
        assert {"sc-with-resize-2": {"online_resize": True, "other": "value"}} in result
        assert {"sc-without-resize": {"online_resize": False, "other": "value"}} not in result

    def test_online_resize_matrix_empty_matrix(self):
        """Test online_resize_matrix with empty matrix"""
        matrix = []

        result = online_resize_matrix(matrix)

        assert result == []


class TestHppMatrix:
    """Test cases for hpp_matrix function"""

    @patch("utilities.pytest_matrix_utils.cache_admin_client")
    @patch("utilities.pytest_matrix_utils.StorageClass")
    def test_hpp_matrix_with_hpp_provisioner(self, mock_storage_class, mock_cache_admin_client):
        """Test hpp_matrix filters storage classes with HPP provisioner"""
        mock_client = MagicMock()
        mock_cache_admin_client.return_value = mock_client

        # Mock StorageClass instances
        mock_sc_hpp = MagicMock()
        mock_sc_hpp.instance.provisioner = "kubevirt.io.hostpath-provisioner"

        mock_sc_non_hpp = MagicMock()
        mock_sc_non_hpp.instance.provisioner = "other.provisioner"

        # Configure StorageClass mock to return different instances
        def storage_class_side_effect(client, name):
            if name == "hpp-sc":
                return mock_sc_hpp
            if name == "non-hpp-sc":
                return mock_sc_non_hpp
            return MagicMock()

        mock_storage_class.side_effect = storage_class_side_effect
        mock_storage_class.Provisioner.HOSTPATH_CSI = "kubevirt.io/hostpath-csi"
        mock_storage_class.Provisioner.HOSTPATH = "kubevirt.io.hostpath-provisioner"

        matrix = [
            {"hpp-sc": {"other": "value"}},
            {"non-hpp-sc": {"other": "value"}},
        ]

        result = hpp_matrix(matrix)

        assert len(result) == 1
        assert {"hpp-sc": {"other": "value"}} in result

    @patch("utilities.pytest_matrix_utils.cache_admin_client")
    @patch("utilities.pytest_matrix_utils.StorageClass")
    def test_hpp_matrix_empty_matrix(self, mock_storage_class, mock_cache_admin_client):
        """Test hpp_matrix with empty matrix"""
        matrix = []

        result = hpp_matrix(matrix)

        assert result == []


class TestWffcMatrix:
    """Test cases for wffc_matrix function"""

    def test_wffc_matrix_with_wffc_enabled(self):
        """Test wffc_matrix filters storage classes with WFFC enabled"""
        matrix = [
            {"sc-with-wffc": {"wffc": True, "other": "value"}},
            {"sc-without-wffc": {"wffc": False, "other": "value"}},
            {"sc-with-wffc-2": {"wffc": True, "other": "value"}},
        ]

        result = wffc_matrix(matrix)

        assert len(result) == 2
        assert {"sc-with-wffc": {"wffc": True, "other": "value"}} in result
        assert {"sc-with-wffc-2": {"wffc": True, "other": "value"}} in result
        assert {"sc-without-wffc": {"wffc": False, "other": "value"}} not in result

    def test_wffc_matrix_empty_matrix(self):
        """Test wffc_matrix with empty matrix"""
        matrix = []

        result = wffc_matrix(matrix)

        assert result == []

    def test_wffc_matrix_no_wffc_enabled(self):
        """Test wffc_matrix with no WFFC enabled storage classes"""
        matrix = [
            {"sc-without-wffc-1": {"wffc": False, "other": "value"}},
            {"sc-without-wffc-2": {"wffc": False, "other": "value"}},
        ]

        result = wffc_matrix(matrix)

        assert result == []


class TestMatrixFunctionSignatures:
    """Test that all matrix functions accept only matrix argument"""

    def test_snapshot_matrix_signature(self):
        """Test snapshot_matrix function signature"""
        import inspect

        sig = inspect.signature(snapshot_matrix)
        params = list(sig.parameters.keys())
        assert params == ["matrix"]

    def test_without_snapshot_capability_matrix_signature(self):
        """Test without_snapshot_capability_matrix function signature"""
        import inspect

        sig = inspect.signature(without_snapshot_capability_matrix)
        params = list(sig.parameters.keys())
        assert params == ["matrix"]

    def test_online_resize_matrix_signature(self):
        """Test online_resize_matrix function signature"""
        import inspect

        sig = inspect.signature(online_resize_matrix)
        params = list(sig.parameters.keys())
        assert params == ["matrix"]

    def test_hpp_matrix_signature(self):
        """Test hpp_matrix function signature"""
        import inspect

        sig = inspect.signature(hpp_matrix)
        params = list(sig.parameters.keys())
        assert params == ["matrix"]

    def test_wffc_matrix_signature(self):
        """Test wffc_matrix function signature"""
        import inspect

        sig = inspect.signature(wffc_matrix)
        params = list(sig.parameters.keys())
        assert params == ["matrix"]
