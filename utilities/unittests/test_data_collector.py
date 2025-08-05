"""Unit tests for data_collector module"""

import json
import os
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

# ==================================================================================
# MODULE MOCKING STRATEGY DOCUMENTATION
# ==================================================================================
#
# CURRENT APPROACH: sys.modules Manipulation for Mock Isolation
#
# Problem Being Solved:
# ---------------------
# The conftest.py file globally mocks certain modules to prevent circular
# dependencies during test collection. However, for these specific unit tests,
# we need to test the REAL implementation of data_collector functions, not mocks.
#
# Why This Approach Is Used:
# -------------------------
# 1. Global mocks in conftest.py are necessary to prevent import errors
# 2. Some tests need the real module implementation to verify actual behavior
# 3. Python's import system caches modules in sys.modules, so simply importing
#    after mocks are set up would still get the mocked version
# 4. Removing from sys.modules forces a fresh import of the real module
#
# Current Implementation:
# ----------------------
# We check if the module is already in sys.modules (indicating it was mocked)
# and remove it to force Python to re-import the real implementation.
#
# FRAGILITY CONCERNS (as noted by CodeRabbit):
# ============================================
# 1. **Import Order Dependency**: This approach is sensitive to the order of
#    test execution and module imports across the test suite
# 2. **Global State Pollution**: Modifying sys.modules affects the entire
#    Python process, potentially impacting other tests
# 3. **Race Conditions**: In parallel test execution, this could cause
#    unpredictable behavior when multiple tests modify sys.modules
# 4. **Hidden Dependencies**: The success of tests depends on implicit
#    knowledge of what's mocked in conftest.py
# 5. **Debugging Difficulty**: Import issues become harder to trace when
#    modules are dynamically removed and re-imported
#
# ALTERNATIVE APPROACHES TO CONSIDER:
# ==================================
#
# 1. **Context Manager Approach**:
#    - Pros: Cleaner scope isolation, automatic cleanup
#    - Cons: Requires refactoring existing test structure
#    - Example:
#      ```python
#      @contextmanager
#      def real_module_import(module_name):
#          original = sys.modules.pop(module_name, None)
#          try:
#              yield
#          finally:
#              if original:
#                  sys.modules[module_name] = original
#      ```
#
# 2. **Separate Test Directories**:
#    - Pros: Complete isolation, no global state manipulation
#    - Cons: Code duplication, more complex project structure
#    - Implementation: Create dedicated test directories with different
#      conftest.py configurations for mocked vs. real imports
#
# 3. **Conditional Mock Setup**:
#    - Pros: More explicit control over when mocks are applied
#    - Cons: Requires significant refactoring of conftest.py
#    - Implementation: Use environment variables or markers to conditionally
#      apply mocks based on test requirements
#
# 4. **Import Hook Manipulation**:
#    - Pros: More sophisticated control over import behavior
#    - Cons: High complexity, potential performance impact
#    - Implementation: Custom import hooks that can selectively return
#      real or mocked modules based on test context
#
# TRADE-OFFS ANALYSIS:
# ===================
# Current Approach:
#   ✓ Simple implementation
#   ✓ Works with existing codebase structure
#   ✓ Minimal changes required
#   ✗ Fragile and order-dependent
#   ✗ Affects global state
#   ✗ Difficult to debug import issues
#
# Context Manager:
#   ✓ Better encapsulation
#   ✓ Automatic cleanup
#   ✗ Requires test refactoring
#   ✗ Still manipulates sys.modules
#
# Separate Directories:
#   ✓ Complete isolation
#   ✓ No global state issues
#   ✗ Code duplication
#   ✗ Complex project structure
#
# RECOMMENDATION FOR FUTURE MAINTAINERS:
# ======================================
# While the current approach works, consider migrating to a context manager
# approach as the next evolutionary step. This would provide better encapsulation
# while requiring minimal changes to the existing test structure.
#
# For now, this approach is maintained for stability, but future refactoring
# should prioritize one of the cleaner alternatives listed above.
# ==================================================================================

# For data_collector tests, we need to import real functions, not mocks
# Remove the mock and import the real module
if "utilities.data_collector" in sys.modules:
    del sys.modules["utilities.data_collector"]

# Circular dependencies are already mocked in conftest.py

# Now import the real data_collector module functions
from utilities.data_collector import (
    BASE_DIRECTORY_NAME,
    collect_alerts_data,
    collect_default_cnv_must_gather_with_vm_gather,
    collect_ocp_must_gather,
    collect_vnc_screenshot_for_vms,
    get_data_collector_base,
    get_data_collector_base_directory,
    get_data_collector_dir,
    prepare_pytest_item_data_dir,
    set_data_collector_directory,
    set_data_collector_values,
    write_to_file,
)


class TestGetDataCollectorBase:
    """Test cases for get_data_collector_base function"""

    def test_get_data_collector_base_with_explicit_dir(self):
        """Test get_data_collector_base with explicit base_dir parameter"""
        result = get_data_collector_base(base_dir="/custom/path")
        assert result == "/custom/path/"

    def test_get_data_collector_base_with_relative_path(self):
        """Test get_data_collector_base with relative path"""
        result = get_data_collector_base(base_dir="relative/path")
        expected = os.path.normpath(os.path.expanduser("relative/path")) + os.sep
        assert result == expected

    @patch.dict(os.environ, {"CNV_TESTS_CONTAINER": "true"})
    def test_get_data_collector_base_container_env(self):
        """Test get_data_collector_base with CNV_TESTS_CONTAINER environment"""
        # Clear cache first
        get_data_collector_base.cache_clear()
        result = get_data_collector_base()
        assert result == "/data/"

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.getcwd")
    def test_get_data_collector_base_current_working_dir(self, mock_getcwd):
        """Test get_data_collector_base defaults to current working directory"""
        mock_getcwd.return_value = "/current/working/dir"
        # Clear cache first
        get_data_collector_base.cache_clear()

        result = get_data_collector_base()
        assert result == "/current/working/dir/"

    def test_get_data_collector_base_already_has_separator(self):
        """Test get_data_collector_base when path already ends with separator"""
        result = get_data_collector_base(base_dir="/path/with/separator/")
        assert result == "/path/with/separator/"

    def test_get_data_collector_base_cache_behavior(self):
        """Test that get_data_collector_base uses cache correctly"""
        # Clear cache first
        get_data_collector_base.cache_clear()

        # First call
        result1 = get_data_collector_base(base_dir="/test/path")
        # Second call with same parameter should return cached result
        result2 = get_data_collector_base(base_dir="/test/path")

        assert result1 == result2 == "/test/path/"


class TestSetDataCollectorValues:
    """Test cases for set_data_collector_values function"""

    @patch("utilities.data_collector.py_config", {})
    @patch("utilities.data_collector.get_data_collector_base")
    def test_set_data_collector_values_with_base_dir(self, mock_get_base):
        """Test set_data_collector_values with base_dir"""
        mock_get_base.return_value = "/custom/base/"

        result = set_data_collector_values(base_dir="/custom/base")

        mock_get_base.assert_called_once_with(base_dir="/custom/base")
        assert result["data_collector_base_directory"] == "/custom/base/tests-collected-info"

    @patch("utilities.data_collector.py_config", {})
    @patch("utilities.data_collector.get_data_collector_base")
    def test_set_data_collector_values_without_base_dir(self, mock_get_base):
        """Test set_data_collector_values without base_dir"""
        mock_get_base.return_value = "/default/base/"

        result = set_data_collector_values()

        mock_get_base.assert_called_once_with(base_dir=None)
        assert result["data_collector_base_directory"] == "/default/base/tests-collected-info"


class TestGetDataCollectorBaseDirectory:
    """Test cases for get_data_collector_base_directory function"""

    @patch(
        "utilities.data_collector.py_config", {"data_collector": {"data_collector_base_directory": "/test/base/dir"}}
    )
    def test_get_data_collector_base_directory(self):
        """Test get_data_collector_base_directory returns correct value"""
        result = get_data_collector_base_directory()
        assert result == "/test/base/dir"


class TestGetDataCollectorDir:
    """Test cases for get_data_collector_dir function"""

    @patch(
        "utilities.data_collector.py_config",
        {
            "data_collector": {
                "collector_directory": "/specific/collector/dir",
                "data_collector_base_directory": "/base/dir",
            }
        },
    )
    def test_get_data_collector_dir_with_collector_directory(self):
        """Test get_data_collector_dir with collector_directory set"""
        result = get_data_collector_dir()
        assert result == "/specific/collector/dir"

    @patch("utilities.data_collector.py_config", {"data_collector": {"data_collector_base_directory": "/base/dir"}})
    def test_get_data_collector_dir_fallback_to_base(self):
        """Test get_data_collector_dir falls back to base directory"""
        result = get_data_collector_dir()
        assert result == "/base/dir"


class TestWriteToFile:
    """Test cases for write_to_file function"""

    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_write_to_file_success(self, mock_file_open, mock_makedirs):
        """Test write_to_file writes content successfully"""
        write_to_file("test.txt", "test content", "/test/dir")

        mock_makedirs.assert_called_once_with("/test/dir", exist_ok=True)
        mock_file_open.assert_called_once_with("/test/dir/test.txt", "w")
        mock_file_open().write.assert_called_once_with("test content")

    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_write_to_file_custom_mode(self, mock_file_open, mock_makedirs):
        """Test write_to_file with custom file mode"""
        write_to_file("test.txt", "content", "/test/dir", mode="a")

        mock_file_open.assert_called_once_with("/test/dir/test.txt", "a")

    @patch("os.makedirs")
    @patch("builtins.open", side_effect=IOError("Permission denied"))
    @patch("utilities.data_collector.LOGGER")
    def test_write_to_file_exception_handling(self, mock_logger, mock_file_open, mock_makedirs):
        """Test write_to_file handles exceptions gracefully"""
        write_to_file("test.txt", "content", "/test/dir")

        # Should log warning when exception occurs
        mock_logger.warning.assert_called_once()
        assert "Failed to write extras to file" in mock_logger.warning.call_args[0][0]


class TestSetDataCollectorDirectory:
    """Test cases for set_data_collector_directory function"""

    @patch("utilities.data_collector.py_config", {"data_collector": {}})
    @patch("utilities.data_collector.prepare_pytest_item_data_dir")
    def test_set_data_collector_directory(self, mock_prepare_dir):
        """Test set_data_collector_directory sets collector directory"""
        mock_item = MagicMock()
        mock_prepare_dir.return_value = "/prepared/dir/path"

        set_data_collector_directory(mock_item, "/output/dir")

        mock_prepare_dir.assert_called_once_with(item=mock_item, output_dir="/output/dir")
        from utilities.data_collector import py_config

        assert py_config["data_collector"]["collector_directory"] == "/prepared/dir/path"


class TestCollectAlertsData:
    """Test cases for collect_alerts_data function"""

    @patch("utilities.data_collector.get_data_collector_dir")
    @patch("utilities.data_collector.utilities.infra.get_prometheus_k8s_token")
    @patch("utilities.data_collector.Prometheus")
    @patch("utilities.data_collector.write_to_file")
    @patch("utilities.data_collector.LOGGER")
    def test_collect_alerts_data(self, mock_logger, mock_write, mock_prometheus_class, mock_get_token, mock_get_dir):
        """Test collect_alerts_data collects and writes alerts"""
        mock_get_dir.return_value = "/test/dir"
        mock_get_token.return_value = "test-token"

        mock_prometheus = MagicMock()
        mock_alerts = [{"alert": "test", "status": "firing"}]
        mock_prometheus.alerts.return_value = mock_alerts
        mock_prometheus_class.return_value = mock_prometheus

        collect_alerts_data()

        mock_get_dir.assert_called_once()
        mock_get_token.assert_called_once_with(duration="900s")
        mock_prometheus_class.assert_called_once_with(verify_ssl=False, bearer_token="test-token")
        mock_prometheus.alerts.assert_called_once()
        mock_write.assert_called_once_with(
            base_directory="/test/dir", file_name="firing_alerts.json", content=json.dumps(mock_alerts)
        )


class TestCollectVncScreenshotForVms:
    """Test cases for collect_vnc_screenshot_for_vms function"""

    @patch("utilities.data_collector.get_data_collector_base_directory")
    @patch("utilities.data_collector.utilities.infra.run_virtctl_command")
    @patch("utilities.data_collector.shlex.split")
    def test_collect_vnc_screenshot_for_vms(self, mock_shlex, mock_run_virtctl, mock_get_base_dir):
        """Test collect_vnc_screenshot_for_vms runs virtctl command"""
        mock_get_base_dir.return_value = "/base/dir"
        mock_shlex.return_value = ["vnc", "screenshot", "test-vm", "-f", "/base/dir/test-ns-test-vm.png"]

        collect_vnc_screenshot_for_vms("test-vm", "test-ns")

        mock_get_base_dir.assert_called_once()
        expected_command = "vnc screenshot test-vm -f /base/dir/test-ns-test-vm.png"
        mock_shlex.assert_called_once_with(expected_command)
        mock_run_virtctl.assert_called_once_with(
            command=["vnc", "screenshot", "test-vm", "-f", "/base/dir/test-ns-test-vm.png"], namespace="test-ns"
        )


class TestCollectOcpMustGather:
    """Test cases for collect_ocp_must_gather function"""

    @patch("utilities.data_collector.get_data_collector_dir")
    @patch("utilities.data_collector.run_must_gather")
    @patch("utilities.data_collector.LOGGER")
    def test_collect_ocp_must_gather(self, mock_logger, mock_run_must_gather, mock_get_dir):
        """Test collect_ocp_must_gather runs must-gather"""
        mock_get_dir.return_value = "/collect/dir"

        collect_ocp_must_gather(3600)

        mock_get_dir.assert_called_once()
        mock_run_must_gather.assert_called_once_with(
            target_base_dir="/collect/dir",
            since="3600s",
            timeout="1200s",  # TIMEOUT_20MIN
        )
        mock_logger.info.assert_called_once()


class TestCollectDefaultCnvMustGatherWithVmGather:
    """Test cases for collect_default_cnv_must_gather_with_vm_gather function"""

    @patch("utilities.data_collector.utilities.hco.get_installed_hco_csv")
    @patch("utilities.data_collector.get_client")
    @patch("utilities.data_collector.Namespace")
    @patch("utilities.data_collector.py_config", {"hco_namespace": "test-hco-ns"})
    @patch("utilities.data_collector.run_must_gather")
    @patch("utilities.data_collector.LOGGER")
    def test_collect_default_cnv_must_gather_with_vm_gather(
        self, mock_logger, mock_run_must_gather, mock_namespace_class, mock_get_client, mock_get_csv
    ):
        """Test collect_default_cnv_must_gather_with_vm_gather"""
        # Setup mocks
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_namespace = MagicMock()
        mock_namespace_class.return_value = mock_namespace

        mock_csv = MagicMock()
        mock_csv.name = "cnv-csv-v1.0.0"
        # Setup related images to test must-gather image selection logic
        # The function filters images where name contains "must-gather" and selects the FIRST match
        # Expected behavior: "must-gather-image" should be selected (first image with "must-gather" in name)
        mock_csv.instance.spec.relatedImages = [
            {"name": "some-image", "image": "quay.io/test/some:latest"},  # Will be ignored (no "must-gather")
            {
                "name": "must-gather-image",
                "image": "quay.io/test/must-gather:latest",
            },  # EXPECTED: Selected (first match)
            {"name": "cnv-must-gather-debug", "image": "quay.io/test/debug-gather:latest"},  # Would match but not first
        ]
        mock_get_csv.return_value = mock_csv

        collect_default_cnv_must_gather_with_vm_gather(1800, "/target/dir")

        mock_get_client.assert_called_once()
        mock_namespace_class.assert_called_once_with(name="test-hco-ns")
        mock_get_csv.assert_called_once_with(admin_client=mock_client, hco_namespace=mock_namespace)

        # ASSERTION: Verify the expected must-gather image selection behavior
        # The function should select "quay.io/test/must-gather:latest" because:
        # 1. It filters relatedImages where image["name"] contains "must-gather"
        # 2. It takes the first ([0]) matching image from the filtered list
        # 3. "must-gather-image" is the first image in the list with "must-gather" in its name
        mock_run_must_gather.assert_called_once_with(
            image_url="quay.io/test/must-gather:latest",
            target_base_dir="/target/dir",
            since="1800s",
            script_name="/usr/bin/gather",
            flag_names="vms_details",
        )


class TestPrepareDataDir:
    """Test cases for prepare_pytest_item_data_dir function"""

    @patch("os.makedirs")
    @patch("os.path.split")
    def test_prepare_pytest_item_data_dir_with_class(self, mock_split, mock_makedirs):
        """Test prepare_pytest_item_data_dir with test class"""
        mock_split.return_value = ("/some/path", "test_dir")

        # Mock pytest item
        mock_item = MagicMock()
        mock_item.cls.__name__ = "TestMyClass"
        mock_item.name = "test_my_function"
        mock_item.fspath.dirname = "/home/user/git/test-repo/tests/test_dir"
        mock_item.fspath.basename = "test_something.py"
        mock_item.session.config.inicfg.get.return_value = "tests"

        result = prepare_pytest_item_data_dir(mock_item, "/output")

        expected_path = "/output/test_dir/test_something/TestMyClass/test_my_function"
        assert result == expected_path
        mock_makedirs.assert_called_once_with(expected_path, exist_ok=True)

    def test_prepare_pytest_item_data_dir_missing_testpaths(self):
        """Test prepare_pytest_item_data_dir raises assertion when testpaths is missing"""
        mock_item = MagicMock()
        mock_item.cls = None  # Set cls to None explicitly
        mock_item.session.config.inicfg.get.return_value = None

        with pytest.raises(AssertionError, match="pytest.ini must include testpaths"):
            prepare_pytest_item_data_dir(mock_item, "/output")

    @patch("os.makedirs")
    @patch("os.path.split")
    def test_prepare_pytest_item_data_dir_without_class(self, mock_split, mock_makedirs):
        """Test prepare_pytest_item_data_dir without test class"""
        mock_split.return_value = ("/some/path", "test_dir")

        # Mock pytest item without class
        mock_item = MagicMock()
        mock_item.cls = None
        mock_item.name = "test_function"
        mock_item.fspath.dirname = "/home/user/git/test-repo/tests/test_dir"
        mock_item.fspath.basename = "test_something.py"
        mock_item.session.config.inicfg.get.return_value = "tests"

        result = prepare_pytest_item_data_dir(mock_item, "/output")

        expected_path = "/output/test_dir/test_something/test_function"
        assert result == expected_path
        mock_makedirs.assert_called_once_with(expected_path, exist_ok=True)


class TestConstants:
    """Test cases for module constants"""

    def test_base_directory_name_constant(self):
        """Test BASE_DIRECTORY_NAME constant value"""
        assert BASE_DIRECTORY_NAME == "tests-collected-info"
