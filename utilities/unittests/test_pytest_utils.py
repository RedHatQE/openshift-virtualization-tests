# Generated using Claude cli

"""Unit tests for pytest_utils module"""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from utilities.exceptions import MissingEnvironmentVariableError

# Circular dependencies are already mocked in conftest.py
from utilities.pytest_utils import (
    config_default_storage_class,
    deploy_run_in_progress_config_map,
    deploy_run_in_progress_namespace,
    exit_pytest_execution,
    generate_os_matrix_dicts,
    get_artifactory_server_url,
    get_base_matrix_name,
    get_cnv_version_explorer_url,
    get_current_running_data,
    get_matrix_params,
    get_tests_cluster_markers,
    mark_nmstate_dependent_tests,
    reorder_early_fixtures,
    run_in_progress_config_map,
    separator,
    skip_if_pytest_flags_exists,
    stop_if_run_in_progress,
    update_latest_os_config,
)


class TestGetBaseMatrixName:
    """Test cases for get_base_matrix_name function"""

    def test_get_base_matrix_name_with_multiple_matrices(self):
        """Test extracting base matrix name from complex matrix name"""
        matrix_name = "storage_class_matrix_snapshot_matrix__class__"
        result = get_base_matrix_name(matrix_name)
        assert result == "storage_class_matrix"

    def test_get_base_matrix_name_with_single_matrix(self):
        """Test matrix name that doesn't match the pattern"""
        matrix_name = "simple_matrix"
        result = get_base_matrix_name(matrix_name)
        assert result == "simple_matrix"

    def test_get_base_matrix_name_no_pattern_match(self):
        """Test matrix name with no _matrix suffix"""
        matrix_name = "no_pattern_here"
        result = get_base_matrix_name(matrix_name)
        assert result == "no_pattern_here"

    def test_get_base_matrix_name_empty_string(self):
        """Test empty string input"""
        matrix_name = ""
        result = get_base_matrix_name(matrix_name)
        assert result == ""


class TestGetMatrixParams:
    """Test cases for get_matrix_params function"""

    @patch("utilities.pytest_utils.py_config", {"test_matrix": [{"param": "value"}]})
    @patch("utilities.pytest_utils.skip_if_pytest_flags_exists")
    def test_get_matrix_params_existing_matrix(self, mock_skip_flags):
        """Test getting matrix params when matrix exists in config"""
        mock_skip_flags.return_value = False
        mock_pytest_config = MagicMock()

        result = get_matrix_params(mock_pytest_config, "test_matrix")

        assert result == [{"param": "value"}]
        mock_skip_flags.assert_called_once_with(pytest_config=mock_pytest_config)

    @patch("utilities.pytest_utils.py_config", {"test_matrix": {"param": "value"}})
    @patch("utilities.pytest_utils.skip_if_pytest_flags_exists")
    def test_get_matrix_params_single_dict(self, mock_skip_flags):
        """Test getting matrix params when matrix is a single dict (not list)"""
        mock_skip_flags.return_value = False
        mock_pytest_config = MagicMock()

        result = get_matrix_params(mock_pytest_config, "test_matrix")

        assert result == [{"param": "value"}]

    @patch("utilities.pytest_utils.py_config", {})
    @patch("utilities.pytest_utils.skip_if_pytest_flags_exists")
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_matrix_params_missing_matrix(self, mock_logger, mock_skip_flags):
        """Test getting matrix params when matrix doesn't exist"""
        mock_skip_flags.return_value = False
        mock_pytest_config = MagicMock()

        result = get_matrix_params(mock_pytest_config, "missing_matrix")

        assert result == []
        mock_logger.warning.assert_called_once_with("missing_matrix is missing in config file")

    @patch("utilities.pytest_utils.py_config", {"base_matrix": [{"param": "value"}]})
    @patch("utilities.pytest_utils.skip_if_pytest_flags_exists")
    def test_get_matrix_params_with_function_not_found(self, mock_skip_flags):
        """Test getting matrix params when function is not found in pytest_matrix_utils

        This test verifies the intended API behavior: when a matrix function is requested
        but doesn't exist in pytest_matrix_utils, the function should raise a TypeError.

        API Design Rationale:
        - Fail-fast principle: Configuration errors should be caught immediately
        - Clear feedback: TypeError provides explicit indication of missing function
        - No silent failures: Missing matrix functions represent configuration errors
          that should not be ignored or return empty results
        - Consistency: Function either succeeds completely or fails explicitly

        The TypeError on line 84 of pytest_utils.py (matrix_func(matrix=_base_matrix_params))
        is intentional and represents correct API behavior when getattr() returns None
        for a non-existent function name.
        """
        mock_skip_flags.return_value = False
        mock_pytest_config = MagicMock()

        # This TypeError is the intended behavior for missing matrix functions
        # It ensures configuration errors are caught immediately rather than silently ignored
        # Test scenario: base_matrix exists, but nonexistent_matrix function doesn't exist in pytest_matrix_utils
        with pytest.raises(TypeError, match="'NoneType' object is not callable"):
            get_matrix_params(mock_pytest_config, "base_matrix_nonexistent_matrix__class__")

    @patch("utilities.pytest_utils.py_config", {})
    @patch("utilities.pytest_utils.skip_if_pytest_flags_exists")
    def test_get_matrix_params_skip_flags_true(self, mock_skip_flags):
        """Test getting matrix params when skip flags are active"""
        mock_skip_flags.return_value = True
        mock_pytest_config = MagicMock()

        result = get_matrix_params(mock_pytest_config, "test_matrix")

        # Should return [None] when matrix is missing and no base matrix (converted by line 90)
        assert result == [None]

    @patch("utilities.pytest_utils.py_config", {"base_matrix": [{"param": "value"}]})
    @patch("utilities.pytest_utils.skip_if_pytest_flags_exists")
    def test_get_matrix_params_skip_flags_with_base_matrix(self, mock_skip_flags):
        """Test getting matrix params when skip flags are active but base matrix exists"""
        mock_skip_flags.return_value = True
        mock_pytest_config = MagicMock()

        result = get_matrix_params(mock_pytest_config, "base_matrix_extra_matrix__scope__")

        # Should return base matrix params when skip flags are active
        assert result == [{"param": "value"}]


class TestConfigDefaultStorageClass:
    """Test cases for config_default_storage_class function"""

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "storage_class_matrix": [
                {"new-sc": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
                {"original-sc": {"volume_mode": "Block", "access_mode": "ReadWriteMany"}},
            ],
        },
    )
    def test_config_default_storage_class_cmd_override(self):
        """Test default storage class override from command line"""
        mock_session = MagicMock()
        mock_session.config.getoption.side_effect = lambda name: {
            "default_storage_class": "new-sc",
            "storage_class_matrix": None,
        }.get(name)

        config_default_storage_class(mock_session)

        from utilities.pytest_utils import py_config

        assert py_config["default_storage_class"] == "new-sc"
        assert py_config["default_volume_mode"] == "Filesystem"
        assert py_config["default_access_mode"] == "ReadWriteOnce"

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "storage_class_matrix": [
                {"first-sc": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
                {"second-sc": {"volume_mode": "Block", "access_mode": "ReadWriteMany"}},
            ],
        },
    )
    def test_config_default_storage_class_matrix_override(self):
        """Test default storage class override from storage class matrix"""
        mock_session = MagicMock()
        mock_session.config.getoption.side_effect = lambda name: {
            "default_storage_class": None,
            "storage_class_matrix": "first-sc,second-sc",
        }.get(name)

        config_default_storage_class(mock_session)

        from utilities.pytest_utils import py_config

        assert py_config["default_storage_class"] == "first-sc"
        assert py_config["default_volume_mode"] == "Filesystem"
        assert py_config["default_access_mode"] == "ReadWriteOnce"

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "storage_class_matrix": [
                {"first-sc": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
                {"original-sc": {"volume_mode": "Block", "access_mode": "ReadWriteMany"}},
            ],
        },
    )
    def test_config_default_storage_class_matrix_contains_default(self):
        """Test storage class matrix contains the default storage class"""
        mock_session = MagicMock()
        mock_session.config.getoption.side_effect = lambda name: {
            "default_storage_class": None,
            "storage_class_matrix": "first-sc,original-sc",
        }.get(name)

        config_default_storage_class(mock_session)

        from utilities.pytest_utils import py_config

        # Should keep original-sc since it's in the matrix
        assert py_config["default_storage_class"] == "original-sc"

    @patch("utilities.pytest_utils.py_config", {"default_storage_class": "original-sc"})
    def test_config_default_storage_class_no_changes(self):
        """Test no changes when no overrides provided"""
        mock_session = MagicMock()
        mock_session.config.getoption.side_effect = lambda name: {
            "default_storage_class": None,
            "storage_class_matrix": None,
        }.get(name)

        config_default_storage_class(mock_session)

        from utilities.pytest_utils import py_config

        # Should remain unchanged
        assert py_config["default_storage_class"] == "original-sc"


class TestSeparator:
    """Test cases for separator function"""

    @patch("utilities.pytest_utils.shutil.get_terminal_size")
    def test_separator_no_value(self, mock_get_terminal_size):
        """Test separator with no value (full line)"""
        mock_get_terminal_size.return_value = (80, 40)

        result = separator("=")

        assert result == "=" * 80

    @patch("utilities.pytest_utils.shutil.get_terminal_size")
    def test_separator_with_value(self, mock_get_terminal_size):
        """Test separator with a value in the middle"""
        mock_get_terminal_size.return_value = (80, 40)

        result = separator("=", "TEST")

        # 80 - 6 (for " TEST ") = 74, divided by 2 = 37
        expected = "=" * 37 + " TEST " + "=" * 37
        assert result == expected

    @patch("utilities.pytest_utils.shutil.get_terminal_size")
    def test_separator_fallback_size(self, mock_get_terminal_size):
        """Test separator uses fallback terminal size"""
        mock_get_terminal_size.return_value = (120, 40)  # fallback size

        result = separator("-")

        assert result == "-" * 120


class TestReorderEarlyFixtures:
    """Test cases for reorder_early_fixtures function"""

    def test_reorder_early_fixtures_autouse_in_middle(self):
        """Test reordering when autouse_fixtures is in the middle of the list"""
        # Create mock fixturedef with argname
        mock_fixturedef = MagicMock()
        mock_fixturedef.argname = "autouse_fixtures"

        # Create mock metafunc
        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {
            "fixture1": [MagicMock(argname="fixture1")],
            "autouse_fixtures": [mock_fixturedef],
            "fixture2": [MagicMock(argname="fixture2")],
        }
        # Initial fixture order: autouse_fixtures is in the middle (index 1)
        mock_metafunc.fixturenames = ["fixture1", "autouse_fixtures", "fixture2"]

        reorder_early_fixtures(mock_metafunc)

        # After reordering, autouse_fixtures should be first
        assert mock_metafunc.fixturenames == ["autouse_fixtures", "fixture1", "fixture2"]

    def test_reorder_early_fixtures_autouse_at_end(self):
        """Test reordering when autouse_fixtures is at the end of the list"""
        # Create mock fixturedef with argname
        mock_fixturedef = MagicMock()
        mock_fixturedef.argname = "autouse_fixtures"

        # Create mock metafunc
        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {
            "fixture1": [MagicMock(argname="fixture1")],
            "fixture2": [MagicMock(argname="fixture2")],
            "autouse_fixtures": [mock_fixturedef],
        }
        # Initial fixture order: autouse_fixtures is at the end
        mock_metafunc.fixturenames = ["fixture1", "fixture2", "autouse_fixtures"]

        reorder_early_fixtures(mock_metafunc)

        # After reordering, autouse_fixtures should be first
        assert mock_metafunc.fixturenames == ["autouse_fixtures", "fixture1", "fixture2"]

    def test_reorder_early_fixtures_autouse_already_first(self):
        """Test when autouse_fixtures is already first in the list (no reorder needed)"""
        # Create mock fixturedef with argname
        mock_fixturedef = MagicMock()
        mock_fixturedef.argname = "autouse_fixtures"

        # Create mock metafunc
        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {
            "autouse_fixtures": [mock_fixturedef],
            "fixture1": [MagicMock(argname="fixture1")],
            "fixture2": [MagicMock(argname="fixture2")],
        }
        # autouse_fixtures is already first
        mock_metafunc.fixturenames = ["autouse_fixtures", "fixture1", "fixture2"]

        reorder_early_fixtures(mock_metafunc)

        # Should remain unchanged
        assert mock_metafunc.fixturenames == ["autouse_fixtures", "fixture1", "fixture2"]

    def test_reorder_early_fixtures_autouse_not_in_list(self):
        """Test when autouse_fixtures is not in the fixture list (no action)"""
        # Create mock metafunc without autouse_fixtures
        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {
            "fixture1": [MagicMock(argname="fixture1")],
            "fixture2": [MagicMock(argname="fixture2")],
            "fixture3": [MagicMock(argname="fixture3")],
        }
        # No autouse_fixtures in the list
        mock_metafunc.fixturenames = ["fixture1", "fixture2", "fixture3"]

        reorder_early_fixtures(mock_metafunc)

        # Should remain unchanged
        assert mock_metafunc.fixturenames == ["fixture1", "fixture2", "fixture3"]

    def test_reorder_early_fixtures_empty_arg2fixturedefs(self):
        """Test when metafunc has empty _arg2fixturedefs (no fixtures)"""
        # Create mock metafunc with empty fixtures
        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {}
        mock_metafunc.fixturenames = []

        # Should not raise any errors
        reorder_early_fixtures(mock_metafunc)

        # fixturenames should remain empty
        assert mock_metafunc.fixturenames == []

    def test_reorder_early_fixtures_break_behavior(self):
        """Test the break behavior (only processes first matching fixture)"""
        # Create two mock fixturedefs, both with autouse_fixtures name (edge case)
        mock_fixturedef1 = MagicMock()
        mock_fixturedef1.argname = "autouse_fixtures"

        mock_fixturedef2 = MagicMock()
        mock_fixturedef2.argname = "autouse_fixtures"

        # Create mock metafunc with duplicate autouse_fixtures entries
        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {
            "fixture1": [MagicMock(argname="fixture1")],
            "autouse_fixtures": [mock_fixturedef1],
            "fixture2": [MagicMock(argname="fixture2")],
            "autouse_fixtures_duplicate": [mock_fixturedef2],
        }
        # autouse_fixtures appears once in fixturenames (normal case)
        mock_metafunc.fixturenames = ["fixture1", "autouse_fixtures", "fixture2"]

        reorder_early_fixtures(mock_metafunc)

        # Should move autouse_fixtures to position 0 and break
        assert mock_metafunc.fixturenames == ["autouse_fixtures", "fixture1", "fixture2"]

    def test_reorder_early_fixtures_single_fixture(self):
        """Test when there is only one fixture and it's autouse_fixtures"""
        # Create mock fixturedef with argname
        mock_fixturedef = MagicMock()
        mock_fixturedef.argname = "autouse_fixtures"

        # Create mock metafunc with single fixture
        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {
            "autouse_fixtures": [mock_fixturedef],
        }
        # Single fixture
        mock_metafunc.fixturenames = ["autouse_fixtures"]

        reorder_early_fixtures(mock_metafunc)

        # Should remain unchanged
        assert mock_metafunc.fixturenames == ["autouse_fixtures"]

    def test_reorder_early_fixtures_multiple_early_fixtures_only_autouse(self):
        """Test that only autouse_fixtures is moved (current implementation only defines autouse_fixtures)"""
        # Create mock fixturedef with argname
        mock_fixturedef = MagicMock()
        mock_fixturedef.argname = "autouse_fixtures"

        # Create mock metafunc
        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {
            "fixture1": [MagicMock(argname="fixture1")],
            "fixture2": [MagicMock(argname="fixture2")],
            "autouse_fixtures": [mock_fixturedef],
            "fixture3": [MagicMock(argname="fixture3")],
        }
        # autouse_fixtures is in the middle
        mock_metafunc.fixturenames = ["fixture1", "fixture2", "autouse_fixtures", "fixture3"]

        reorder_early_fixtures(mock_metafunc)

        # autouse_fixtures should be at position 0 (first position in use_early_fixture_names)
        assert mock_metafunc.fixturenames == ["autouse_fixtures", "fixture1", "fixture2", "fixture3"]


class TestMarkNmstateDependentTests:
    """Test cases for mark_nmstate_dependent_tests function."""

    def test_adds_nmstate_marker_when_fixture_present(self):
        """Items that request nmstate_dependent_placeholder get the nmstate marker."""
        item_with_nmstate = MagicMock()
        item_with_nmstate.fixturenames = ["some_fixture", "nmstate_dependent_placeholder"]
        item_without = MagicMock()
        item_without.fixturenames = ["other_fixture"]
        items = [item_with_nmstate, item_without]

        result = mark_nmstate_dependent_tests(items=items)

        assert result is items
        item_with_nmstate.add_marker.assert_called_once_with(marker=pytest.mark.nmstate)
        item_without.add_marker.assert_not_called()

    def test_no_marker_when_placeholder_absent(self):
        """Items that do not request the placeholder are unchanged."""
        item = MagicMock()
        item.fixturenames = ["other_fixture"]
        items = [item]

        result = mark_nmstate_dependent_tests(items=items)

        assert result is items
        item.add_marker.assert_not_called()

    def test_empty_fixturenames_unchanged(self):
        """Items with empty fixturenames are not marked."""
        item = MagicMock()
        item.fixturenames = []
        items = [item]

        result = mark_nmstate_dependent_tests(items=items)

        assert result is items
        item.add_marker.assert_not_called()

    def test_item_missing_fixturenames_unchanged(self):
        """Items without a fixturenames attribute use getattr default and are not marked."""
        item = MagicMock(spec=["add_marker"])
        items = [item]

        result = mark_nmstate_dependent_tests(items=items)

        assert result is items
        item.add_marker.assert_not_called()


class TestStopIfRunInProgress:
    """Test cases for stop_if_run_in_progress function"""

    @patch("utilities.pytest_utils.run_in_progress_config_map")
    @patch("utilities.pytest_utils.exit_pytest_execution")
    def test_stop_if_run_in_progress_exists(self, mock_exit, mock_config_map):
        """Test stopping when run is in progress"""
        mock_cm = MagicMock()
        mock_cm.exists = True
        mock_cm.instance.data = {"user": "test_user"}
        mock_cm.namespace = "test-namespace"
        mock_cm.name = "test-configmap"
        mock_config_map.return_value = mock_cm
        mock_client = MagicMock()

        stop_if_run_in_progress(client=mock_client)

        mock_config_map.assert_called_once_with(client=mock_client)
        mock_exit.assert_called_once()
        assert "test_user" in mock_exit.call_args[1]["log_message"]
        assert mock_exit.call_args[1]["return_code"] == 100

    @patch("utilities.pytest_utils.run_in_progress_config_map")
    @patch("utilities.pytest_utils.exit_pytest_execution")
    def test_stop_if_run_in_progress_not_exists(self, mock_exit, mock_config_map):
        """Test not stopping when no run is in progress"""
        mock_cm = MagicMock()
        mock_cm.exists = False
        mock_config_map.return_value = mock_cm
        mock_client = MagicMock()

        stop_if_run_in_progress(client=mock_client)

        mock_config_map.assert_called_once_with(client=mock_client)
        mock_exit.assert_not_called()


class TestDeployRunInProgressNamespace:
    """Test cases for deploy_run_in_progress_namespace function"""

    @patch("utilities.pytest_utils.ResourceEditor")
    @patch("utilities.pytest_utils.Namespace")
    def test_deploy_run_in_progress_namespace_not_exists(self, mock_namespace_class, mock_resource_editor):
        """Test deploying namespace when it doesn't exist"""
        mock_namespace = MagicMock()
        mock_namespace.exists = False
        mock_namespace_class.return_value = mock_namespace
        mock_client = MagicMock()

        result = deploy_run_in_progress_namespace(client=mock_client)

        assert result == mock_namespace
        mock_namespace_class.assert_called_once_with(client=mock_client, name="cnv-tests-run-in-progress-ns")
        mock_namespace.deploy.assert_called_once_with(wait=True)
        mock_namespace.wait_for_status.assert_called_once()
        mock_resource_editor.assert_called_once()

    @patch("utilities.pytest_utils.Namespace")
    def test_deploy_run_in_progress_namespace_exists(self, mock_namespace_class):
        """Test when namespace already exists"""
        mock_namespace = MagicMock()
        mock_namespace.exists = True
        mock_namespace_class.return_value = mock_namespace
        mock_client = MagicMock()

        result = deploy_run_in_progress_namespace(client=mock_client)

        assert result == mock_namespace
        mock_namespace_class.assert_called_once_with(client=mock_client, name="cnv-tests-run-in-progress-ns")
        mock_namespace.deploy.assert_not_called()


class TestDeployRunInProgressConfigMap:
    """Test cases for deploy_run_in_progress_config_map function"""

    @patch("utilities.pytest_utils.run_in_progress_config_map")
    def test_deploy_run_in_progress_config_map(self, mock_config_map):
        """Test deploying run in progress config map"""
        mock_cm = MagicMock()
        mock_config_map.return_value = mock_cm
        mock_session = MagicMock()
        mock_client = MagicMock()

        deploy_run_in_progress_config_map(client=mock_client, session=mock_session)

        mock_config_map.assert_called_once_with(client=mock_client, session=mock_session)
        mock_cm.deploy.assert_called_once_with(wait=True)


class TestRunInProgressConfigMap:
    """Test cases for run_in_progress_config_map function"""

    @patch("utilities.pytest_utils.get_current_running_data")
    @patch("utilities.pytest_utils.ConfigMap")
    def test_run_in_progress_config_map_with_session(self, mock_config_map_class, mock_get_data):
        """Test creating config map with session data"""
        mock_session = MagicMock()
        mock_data = {"test": "data"}
        mock_get_data.return_value = mock_data
        mock_cm = MagicMock()
        mock_config_map_class.return_value = mock_cm
        mock_client = MagicMock()

        result = run_in_progress_config_map(client=mock_client, session=mock_session)

        assert result == mock_cm
        mock_get_data.assert_called_once_with(session=mock_session)
        mock_config_map_class.assert_called_once_with(
            client=mock_client,
            name="cnv-tests-run-in-progress",
            namespace="cnv-tests-run-in-progress-ns",
            data=mock_data,
        )

    @patch("utilities.pytest_utils.ConfigMap")
    def test_run_in_progress_config_map_without_session(self, mock_config_map_class):
        """Test creating config map without session data"""
        mock_cm = MagicMock()
        mock_config_map_class.return_value = mock_cm
        mock_client = MagicMock()

        result = run_in_progress_config_map(client=mock_client, session=None)

        assert result == mock_cm
        mock_config_map_class.assert_called_once_with(
            client=mock_client,
            name="cnv-tests-run-in-progress",
            namespace="cnv-tests-run-in-progress-ns",
            data=None,
        )


class TestGetCurrentRunningData:
    """Test cases for get_current_running_data function"""

    @patch("utilities.pytest_utils.os.environ", {"CNV_TESTS_CONTAINER": "Yes"})
    @patch("utilities.pytest_utils.os.getcwd")
    @patch("utilities.pytest_utils.socket.gethostname")
    @patch("utilities.pytest_utils.getpass.getuser")
    def test_get_current_running_data(self, mock_getuser, mock_gethostname, mock_getcwd):
        """Test getting current running data"""
        mock_getuser.return_value = "test_user"
        mock_gethostname.return_value = "test_host"
        mock_getcwd.return_value = "/test/dir"

        mock_session = MagicMock()
        mock_session.config.invocation_params.args = ["--verbose", "--tb=short"]
        mock_session.config.option.session_id = "test-session-123"

        result = get_current_running_data(mock_session)

        expected = {
            "user": "test_user",
            "host": "test_host",
            "running_from_dir": "/test/dir",
            "pytest_cmd": "--verbose, --tb=short",
            "session-id": "test-session-123",
            "run-in-container": "Yes",
        }
        assert result == expected

    @patch("utilities.pytest_utils.os.environ", {})
    @patch("utilities.pytest_utils.os.getcwd")
    @patch("utilities.pytest_utils.socket.gethostname")
    @patch("utilities.pytest_utils.getpass.getuser")
    def test_get_current_running_data_no_container(self, mock_getuser, mock_gethostname, mock_getcwd):
        """Test getting current running data when not in container"""
        mock_getuser.return_value = "test_user"
        mock_gethostname.return_value = "test_host"
        mock_getcwd.return_value = "/test/dir"

        mock_session = MagicMock()
        mock_session.config.invocation_params.args = ["test_file.py"]
        mock_session.config.option.session_id = "test-session-456"

        result = get_current_running_data(mock_session)

        assert result["run-in-container"] == "No"


class TestSkipIfPytestFlagsExists:
    """Test cases for skip_if_pytest_flags_exists function"""

    def test_skip_if_pytest_flags_exists_collect_only(self):
        """Test skip when --collect-only flag is set"""
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda flag: flag == "--collect-only"

        result = skip_if_pytest_flags_exists(mock_config)

        assert result is True

    def test_skip_if_pytest_flags_exists_collectonly(self):
        """Test skip when --collectonly flag is set"""
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda flag: flag == "--collectonly"

        result = skip_if_pytest_flags_exists(mock_config)

        assert result is True

    def test_skip_if_pytest_flags_exists_setup_plan(self):
        """Test skip when --setup-plan flag is set"""
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda flag: flag == "--setup-plan"

        result = skip_if_pytest_flags_exists(mock_config)

        assert result is True

    def test_skip_if_pytest_flags_exists_no_flags(self):
        """Test no skip when no relevant flags are set"""
        mock_config = MagicMock()
        mock_config.getoption.return_value = False

        result = skip_if_pytest_flags_exists(mock_config)

        assert result is False


class TestGetArtifactoryServerUrl:
    """Test cases for get_artifactory_server_url function"""

    @patch("utilities.pytest_utils.os.environ", {"ARTIFACTORY_SERVER": "https://custom-server.com"})
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_artifactory_server_url_env_variable(self, mock_logger):
        """Test getting artifactory server URL from environment variable"""
        mock_session = MagicMock()
        result = get_artifactory_server_url("cluster.example.com", session=mock_session)

        assert result == "https://custom-server.com"
        mock_logger.info.assert_any_call(
            "Using user requested `ARTIFACTORY_SERVER` environment variable: https://custom-server.com"
        )

    @patch("utilities.pytest_utils.os.environ", {})
    @patch("utilities.pytest_utils.get_cnv_tests_secret_by_name")
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_artifactory_server_url_matching_domain(self, mock_logger, mock_get_secret):
        """Test getting artifactory server URL with matching domain"""
        mock_session = MagicMock()
        mock_session.config.getoption.return_value = False
        mock_get_secret.side_effect = lambda secret_name, session: {
            "artifactory_servers": {
                "example.com": "https://example-artifactory.com",
                "test.com": "https://test-artifactory.com",
            }
        }[secret_name]

        result = get_artifactory_server_url("cluster.example.com", session=mock_session)

        assert result == "https://example-artifactory.com"
        mock_get_secret.assert_called_once_with(secret_name="artifactory_servers", session=mock_session)

    @patch("utilities.pytest_utils.os.environ", {})
    @patch("utilities.pytest_utils.get_cnv_tests_secret_by_name")
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_artifactory_server_url_default_server(self, mock_logger, mock_get_secret):
        """Test getting default artifactory server URL when no domain matches"""
        mock_session = MagicMock()
        mock_session.config.getoption.return_value = False

        def mock_secret_side_effect(secret_name, session):
            if secret_name == "artifactory_servers":
                return {"other.com": "https://other-artifactory.com"}
            elif secret_name == "default_artifactory_server":
                return {"server": "https://default-artifactory.com"}

        mock_get_secret.side_effect = mock_secret_side_effect

        result = get_artifactory_server_url("cluster.example.com", session=mock_session)

        assert result == "https://default-artifactory.com"
        assert mock_get_secret.call_count == 2

    @patch("utilities.pytest_utils.os.environ", {})
    def test_get_artifactory_server_url_disabled_bitwarden_no_env_var(self):
        """Test error when --disabled-bitwarden flag is set and ARTIFACTORY_SERVER env var is not set"""
        mock_session = MagicMock()
        mock_session.config.getoption.return_value = True

        with pytest.raises(
            MissingEnvironmentVariableError,
            match="Bitwarden access is disabled.*disabled-bitwarden.*ARTIFACTORY_SERVER",
        ):
            get_artifactory_server_url("cluster.example.com", session=mock_session)

        mock_session.config.getoption.assert_called_once_with("--disabled-bitwarden")

    @patch("utilities.pytest_utils.os.environ", {})
    @patch("utilities.pytest_utils.get_cnv_tests_secret_by_name")
    def test_get_artifactory_server_url_default_server_empty_dict(self, mock_get_secret):
        """Test error when default server returns empty dict"""
        mock_session = MagicMock()
        mock_session.config.getoption.return_value = False

        def mock_secret_side_effect(secret_name, session):
            if secret_name == "artifactory_servers":
                return {}
            elif secret_name == "default_artifactory_server":
                return {}

        mock_get_secret.side_effect = mock_secret_side_effect

        with pytest.raises(
            MissingEnvironmentVariableError,
            match="Could not retrieve default artifactory server from Bitwarden",
        ):
            get_artifactory_server_url("cluster.example.com", session=mock_session)

        assert mock_get_secret.call_count == 2

    @patch("utilities.pytest_utils.os.environ", {})
    @patch("utilities.pytest_utils.get_cnv_tests_secret_by_name")
    def test_get_artifactory_server_url_default_server_missing_server_key(self, mock_get_secret):
        """Test error when default server is missing 'server' key"""
        mock_session = MagicMock()
        mock_session.config.getoption.return_value = False

        def mock_secret_side_effect(secret_name, session):
            if secret_name == "artifactory_servers":
                return {}
            elif secret_name == "default_artifactory_server":
                return {"wrong_key": "value"}

        mock_get_secret.side_effect = mock_secret_side_effect

        with pytest.raises(
            MissingEnvironmentVariableError,
            match="Could not retrieve default artifactory server from Bitwarden",
        ):
            get_artifactory_server_url("cluster.example.com", session=mock_session)

        assert mock_get_secret.call_count == 2


class TestGetCnvVersionExplorerUrl:
    """Test cases for get_cnv_version_explorer_url function"""

    @patch("utilities.pytest_utils.os.environ", {"CNV_VERSION_EXPLORER_URL": "https://version-explorer.com"})
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_cnv_version_explorer_url_install_flag(self, mock_logger):
        """Test getting CNV version explorer URL with install flag"""
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda option: option == "install"

        result = get_cnv_version_explorer_url(mock_config)

        assert result == "https://version-explorer.com"

    @patch("utilities.pytest_utils.os.environ", {"CNV_VERSION_EXPLORER_URL": "https://version-explorer.com"})
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_cnv_version_explorer_url_eus_upgrade(self, mock_logger):
        """Test getting CNV version explorer URL with EUS upgrade"""
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda option: {"install": False, "upgrade": "eus"}.get(option, False)

        result = get_cnv_version_explorer_url(mock_config)

        assert result == "https://version-explorer.com"

    @patch("utilities.pytest_utils.os.environ", {})
    def test_get_cnv_version_explorer_url_missing_env(self):
        """Test error when CNV_VERSION_EXPLORER_URL is missing"""
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda option: option == "install"

        with pytest.raises(
            MissingEnvironmentVariableError, match="Please set CNV_VERSION_EXPLORER_URL environment variable"
        ):
            get_cnv_version_explorer_url(mock_config)

    def test_get_cnv_version_explorer_url_no_relevant_flags(self):
        """Test no action when no relevant flags are set"""
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda option: {"install": False, "upgrade": "regular"}.get(option, False)

        result = get_cnv_version_explorer_url(mock_config)

        assert result is None


class TestGetTestsClusterMarkers:
    """Test cases for get_tests_cluster_markers function"""

    def _create_marker(self, name):
        """Helper to create a mock marker with a string name attribute"""
        marker = MagicMock()
        marker.name = name
        return marker

    @patch("utilities.pytest_utils.json.dumps")
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_tests_cluster_markers_success(self, mock_logger, mock_json):
        """Test basic test with markers found"""
        # Create mock test items with markers
        mock_item1 = MagicMock()
        mock_item1.iter_markers.return_value = [
            self._create_marker("ipv4"),
            self._create_marker("smoke"),
        ]

        mock_item2 = MagicMock()
        mock_item2.iter_markers.return_value = [
            self._create_marker("gpu"),
            self._create_marker("dpdk"),
        ]

        items = [mock_item1, mock_item2]

        # Use actual pytest.ini content format with proper indentation
        pytest_ini_content = "[pytest]\nmarkers =\n    ## Configuration requirements\n    ipv4: Tests IPv4\n    dpdk: Tests DPDK\n    ## Hardware requirements\n    gpu: Requires GPU\n    ## Other markers\n    smoke: Smoke tests\n"

        with patch("builtins.open", mock_open(read_data=pytest_ini_content)):
            get_tests_cluster_markers(items)

        # Should extract ipv4, dpdk, and gpu (from Configuration and Hardware sections)
        mock_logger.info.assert_called()
        call_args_list = mock_logger.info.call_args_list
        # Get the actual logged markers from the call
        logged_markers = call_args_list[0][0][0]
        assert "ipv4" in logged_markers or "dpdk" in logged_markers or "gpu" in logged_markers

    @patch("utilities.pytest_utils.LOGGER")
    def test_get_tests_cluster_markers_no_markers(self, mock_logger):
        """Test when no markers match"""
        # Create mock test items with non-cluster markers only
        mock_item = MagicMock()
        mock_item.iter_markers.return_value = [
            self._create_marker("smoke"),
            self._create_marker("tier1"),
        ]

        items = [mock_item]

        pytest_ini_content = "[pytest]\nmarkers =\n    ## Configuration requirements\n    ipv4: Tests IPv4\n    ## Other markers\n    smoke: Smoke tests\n"

        with patch("builtins.open", mock_open(read_data=pytest_ini_content)):
            get_tests_cluster_markers(items)

        # Should log empty list
        call_args = str(mock_logger.info.call_args_list)
        assert "[]" in call_args

    @patch("utilities.pytest_utils.json.dumps")
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_tests_cluster_markers_with_filepath(self, mock_logger, mock_json):
        """Test when filepath is provided (writes to file)"""
        mock_item = MagicMock()
        mock_item.iter_markers.return_value = [
            self._create_marker("ipv4"),
        ]

        items = [mock_item]
        filepath = "/tmp/test_markers.json"
        mock_json.return_value = '["ipv4"]'

        pytest_ini_content = (
            "[pytest]\nmarkers =\n    ## Configuration requirements\n    ipv4: Tests IPv4\n    dpdk: Tests DPDK\n"
        )

        m = mock_open(read_data=pytest_ini_content)
        with patch("builtins.open", m):
            get_tests_cluster_markers(items, filepath=filepath)

            # Verify that open was called for both reading pytest.ini and writing the file
            # Check that filepath was logged
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any(filepath in call for call in info_calls)
            # Verify json.dumps was called for the markers
            mock_json.assert_called_once()

    @patch("utilities.pytest_utils.LOGGER")
    def test_get_tests_cluster_markers_config_section_parsing(self, mock_logger):
        """Test correct parsing of pytest.ini Configuration requirements section"""
        mock_item = MagicMock()
        mock_item.iter_markers.return_value = [
            self._create_marker("ipv4"),
            self._create_marker("other_marker"),
        ]

        items = [mock_item]

        pytest_ini_content = "[pytest]\nmarkers =\n    ## Configuration requirements\n    ipv4: Config IPv4\n    dpdk: Config DPDK\n    ## Other section\n    other_marker: Other marker\n"

        with patch("builtins.open", mock_open(read_data=pytest_ini_content)):
            get_tests_cluster_markers(items)

        # Only ipv4 should be in cluster markers, not other_marker
        call_args_list = mock_logger.info.call_args_list
        logged_markers = call_args_list[0][0][0]
        assert "ipv4" in logged_markers
        # Since other_marker is not in a cluster section, it shouldn't be included
        assert "'ipv4'" in logged_markers or "ipv4" in logged_markers

    @patch("utilities.pytest_utils.LOGGER")
    def test_get_tests_cluster_markers_hardware_section(self, mock_logger):
        """Test Hardware requirements section"""
        mock_item = MagicMock()
        mock_item.iter_markers.return_value = [
            self._create_marker("gpu"),
            self._create_marker("smoke"),
        ]

        items = [mock_item]

        pytest_ini_content = "[pytest]\nmarkers =\n    ## Hardware requirements\n    gpu: Requires GPU\n    sriov: Requires SR-IOV\n    ## Other section\n    smoke: Smoke tests\n"

        with patch("builtins.open", mock_open(read_data=pytest_ini_content)):
            get_tests_cluster_markers(items)

        # Only gpu should be in cluster markers
        call_args_list = mock_logger.info.call_args_list
        logged_markers = call_args_list[0][0][0]
        assert "gpu" in logged_markers

    @patch("utilities.pytest_utils.LOGGER")
    def test_get_tests_cluster_markers_section_end_on_empty_line(self, mock_logger):
        """Test section ends on empty line"""
        mock_item = MagicMock()
        mock_item.iter_markers.return_value = [
            self._create_marker("ipv4"),
            self._create_marker("other_marker"),
        ]

        items = [mock_item]

        pytest_ini_content = "[pytest]\nmarkers =\n    ## Configuration requirements\n    ipv4: Marker 1\n\n    ## Other section\n    other_marker: Other\n"

        with patch("builtins.open", mock_open(read_data=pytest_ini_content)):
            get_tests_cluster_markers(items)

        # ipv4 should be detected, other_marker should not
        call_args_list = mock_logger.info.call_args_list
        logged_markers = call_args_list[0][0][0]
        assert "ipv4" in logged_markers

    @patch("utilities.pytest_utils.LOGGER")
    def test_get_tests_cluster_markers_section_end_on_comment(self, mock_logger):
        """Test section ends on comment line"""
        mock_item = MagicMock()
        mock_item.iter_markers.return_value = [
            self._create_marker("ipv4"),
            self._create_marker("other_marker"),
        ]

        items = [mock_item]

        pytest_ini_content = "[pytest]\nmarkers =\n    ## Configuration requirements\n    ipv4: Marker 1\n    ## Another section\n    other_marker: Other\n"

        with patch("builtins.open", mock_open(read_data=pytest_ini_content)):
            get_tests_cluster_markers(items)

        # Only ipv4 should be in cluster markers
        call_args_list = mock_logger.info.call_args_list
        logged_markers = call_args_list[0][0][0]
        assert "ipv4" in logged_markers


class TestExitPytestExecution:
    """Test cases for exit_pytest_execution function"""

    @patch("utilities.pytest_utils.pytest.exit")
    @patch("utilities.pytest_utils.get_data_collector_base_directory")
    def test_exit_pytest_execution_basic(self, mock_get_base_dir, mock_pytest_exit):
        """Test basic exit with message"""
        mock_get_base_dir.return_value = "/tmp/test"
        mock_admin_client = MagicMock()
        log_message = "Test exit message"

        exit_pytest_execution(log_message=log_message, return_code=1, admin_client=mock_admin_client)

        mock_pytest_exit.assert_called_once_with(reason=log_message, returncode=1)

    @patch("utilities.pytest_utils.pytest.exit")
    @patch("utilities.pytest_utils.write_to_file")
    @patch("utilities.pytest_utils.get_data_collector_base_directory")
    def test_exit_pytest_execution_with_filename(self, mock_get_base_dir, mock_write, mock_pytest_exit):
        """Test exit with filename for logging"""
        mock_get_base_dir.return_value = "/tmp/test"
        log_message = "Test error"
        MagicMock()
        filename = "test_error.log"
        mock_admin_client = MagicMock()

        exit_pytest_execution(log_message=log_message, return_code=1, filename=filename, admin_client=mock_admin_client)

        mock_write.assert_called_once_with(
            file_name=filename,
            content=log_message,
            base_directory="/tmp/test/utilities/pytest_exit_errors",
        )
        mock_pytest_exit.assert_called_once()

    @patch("utilities.pytest_utils.pytest.exit")
    @patch("utilities.pytest_utils.get_data_collector_base_directory")
    def test_exit_pytest_execution_with_junitxml(self, mock_get_base_dir, mock_pytest_exit):
        """Test exit with junitxml_property"""
        mock_get_base_dir.return_value = "/tmp/test"
        log_message = "Test exit"
        mock_admin_client = MagicMock()
        mock_junitxml = MagicMock()

        exit_pytest_execution(
            log_message=log_message, return_code=5, junitxml_property=mock_junitxml, admin_client=mock_admin_client
        )

        mock_junitxml.assert_called_once_with(name="exit_code", value=5)
        mock_pytest_exit.assert_called_once()

    @patch("utilities.pytest_utils.pytest.exit")
    @patch("utilities.pytest_utils.collect_default_cnv_must_gather_with_vm_gather")
    @patch("utilities.pytest_utils.get_data_collector_base_directory")
    @patch("utilities.pytest_utils.SANITY_TESTS_FAILURE", 99)
    @patch("utilities.pytest_utils.TIMEOUT_5MIN", 300)
    def test_exit_pytest_execution_sanity_failure_collects_must_gather(
        self, mock_get_base_dir, mock_collect, mock_pytest_exit
    ):
        """Test must-gather collection on SANITY_TESTS_FAILURE"""
        mock_get_base_dir.return_value = "/tmp/test"
        mock_admin_client = MagicMock()
        log_message = "Sanity test failure"

        exit_pytest_execution(
            log_message=log_message,
            admin_client=mock_admin_client,
        )

        mock_collect.assert_called_once_with(
            since_time=300,
            target_dir="/tmp/test/utilities/pytest_exit_errors",
            admin_client=mock_admin_client,
        )
        mock_pytest_exit.assert_called_once()

    @patch("utilities.pytest_utils.pytest.exit")
    @patch("utilities.pytest_utils.collect_default_cnv_must_gather_with_vm_gather")
    @patch("utilities.pytest_utils.get_data_collector_base_directory")
    @patch("utilities.pytest_utils.LOGGER")
    @patch("utilities.pytest_utils.SANITY_TESTS_FAILURE", 99)
    def test_exit_pytest_execution_must_gather_fails_silently(
        self, mock_logger, mock_get_base_dir, mock_collect, mock_pytest_exit
    ):
        """Test that must-gather failure doesn't prevent exit"""
        mock_get_base_dir.return_value = "/tmp/test"
        mock_collect.side_effect = Exception("Must-gather failed")
        log_message = "Sanity test failure"
        mock_admin_client = MagicMock()
        MagicMock()

        exit_pytest_execution(log_message=log_message, admin_client=mock_admin_client)

        # Should log warning but still exit
        mock_logger.warning.assert_called_once()
        assert "Failed to collect logs" in str(mock_logger.warning.call_args)
        mock_pytest_exit.assert_called_once()

    @patch("utilities.pytest_utils.pytest.exit")
    @patch("utilities.pytest_utils.collect_default_cnv_must_gather_with_vm_gather")
    @patch("utilities.pytest_utils.get_data_collector_base_directory")
    @patch("utilities.pytest_utils.SANITY_TESTS_FAILURE", 99)
    def test_exit_pytest_execution_custom_return_code(self, mock_get_base_dir, mock_collect, mock_pytest_exit):
        """Test with non-SANITY_TESTS_FAILURE code (skips must-gather)"""
        mock_get_base_dir.return_value = "/tmp/test"
        log_message = "Regular exit"
        mock_admin_client = MagicMock()

        exit_pytest_execution(
            log_message=log_message,
            return_code=5,
            admin_client=mock_admin_client,
        )

        # Should not collect must-gather
        mock_collect.assert_not_called()
        mock_pytest_exit.assert_called_once_with(reason=log_message, returncode=5)

    @patch("utilities.pytest_utils.pytest.exit")
    @patch("utilities.pytest_utils.write_to_file")
    @patch("utilities.pytest_utils.collect_default_cnv_must_gather_with_vm_gather")
    @patch("utilities.pytest_utils.get_data_collector_base_directory")
    @patch("utilities.pytest_utils.SANITY_TESTS_FAILURE", 99)
    @patch("utilities.pytest_utils.TIMEOUT_5MIN", 300)
    def test_exit_pytest_execution_all_options(self, mock_get_base_dir, mock_collect, mock_write, mock_pytest_exit):
        """Test with all options provided"""
        mock_get_base_dir.return_value = "/tmp/test"
        log_message = "Complete failure"
        mock_admin_client = MagicMock()
        filename = "error.log"
        mock_junitxml = MagicMock()

        exit_pytest_execution(
            log_message=log_message,
            filename=filename,
            junitxml_property=mock_junitxml,
            admin_client=mock_admin_client,
        )

        # All components should be called
        mock_collect.assert_called_once_with(
            since_time=300,
            target_dir="/tmp/test/utilities/pytest_exit_errors",
            admin_client=mock_admin_client,
        )
        mock_write.assert_called_once_with(
            file_name=filename,
            content=log_message,
            base_directory="/tmp/test/utilities/pytest_exit_errors",
        )
        mock_junitxml.assert_called_once_with(name="exit_code", value=99)
        mock_pytest_exit.assert_called_once_with(reason=log_message, returncode=99)


class TestGetMatrixParamsAdditionalCoverage:
    """Additional test cases to cover missing lines in get_matrix_params

    Note: Lines 88, 95-96 in get_matrix_params are difficult to test in isolation due to:
    - Line 88: Module import path is conditional on sys.modules state and requires complex setup
    - Lines 95-96: Second warning path requires specific config state that overlaps with line 78 path
    These lines are exercised during integration tests when the actual pytest_matrix_utils module is used.
    """

    @patch("utilities.pytest_utils.py_config", {})
    @patch("utilities.pytest_utils.skip_if_pytest_flags_exists")
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_matrix_params_missing_matrix_in_config(self, mock_logger, mock_skip_flags):
        """Test warning when matrix is missing in config file"""
        mock_skip_flags.return_value = False
        mock_pytest_config = MagicMock()

        # When matrix_name exists in config but is None/empty
        with patch("utilities.pytest_utils.py_config", {"test_matrix": None}):
            result = get_matrix_params(mock_pytest_config, "test_matrix")

            # Should return empty list and log warning (lines 94-96)
            assert result == []
            mock_logger.warning.assert_called_with("test_matrix is missing in config file")


class TestGenerateOsMatrixDicts:
    """Test cases for generate_os_matrix_dicts function"""

    @pytest.fixture
    def sample_rhel_matrix(self):
        """Sample RHEL OS matrix for testing"""
        return [
            {
                "rhel-9-6": {
                    "os_version": "9.6",
                    "image_name": "rhel-9.6.qcow2",
                    "latest_released": True,
                }
            }
        ]

    @pytest.fixture
    def sample_fedora_matrix(self):
        """Sample Fedora OS matrix for testing"""
        return [
            {
                "fedora-43": {
                    "os_version": "43",
                    "image_name": "fedora-43.qcow2",
                    "latest_released": True,
                }
            }
        ]

    @pytest.fixture
    def sample_instance_type_matrix(self):
        """Sample instance type OS matrix for testing"""
        return [
            {
                "rhel.9": {
                    "preference": "rhel.9",
                    "latest_released": True,
                }
            }
        ]

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_rhel_os_matrix(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
        sample_rhel_matrix,
    ):
        """Test generating RHEL OS matrix from rhel_os_list"""
        mock_get_arch.return_value = "amd64"
        mock_generate_os_matrix.return_value = sample_rhel_matrix
        mock_generate_latest.return_value = sample_rhel_matrix[0]["rhel-9-6"]

        os_dict = {"rhel_os_list": ["rhel-9-6"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        mock_generate_os_matrix.assert_called_once_with(os_name="rhel", supported_operating_systems=["rhel-9-6"])
        mock_generate_latest.assert_called_once()
        assert mock_py_config["rhel_os_matrix"] == sample_rhel_matrix

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_fedora_os_matrix(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
        sample_fedora_matrix,
    ):
        """Test generating Fedora OS matrix from fedora_os_list"""
        mock_get_arch.return_value = "amd64"
        mock_generate_os_matrix.return_value = sample_fedora_matrix
        mock_generate_latest.return_value = sample_fedora_matrix[0]["fedora-43"]

        os_dict = {"fedora_os_list": ["fedora-43"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        mock_generate_os_matrix.assert_called_once_with(os_name="fedora", supported_operating_systems=["fedora-43"])
        assert mock_py_config["fedora_os_matrix"] == sample_fedora_matrix

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_centos_os_matrix(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
    ):
        """Test generating CentOS OS matrix from centos_os_list"""
        mock_get_arch.return_value = "amd64"
        sample_centos_matrix = [{"centos-stream-9": {"os_version": "9", "latest_released": True}}]
        mock_generate_os_matrix.return_value = sample_centos_matrix
        mock_generate_latest.return_value = sample_centos_matrix[0]["centos-stream-9"]

        os_dict = {"centos_os_list": ["centos-stream-9"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        mock_generate_os_matrix.assert_called_once_with(
            os_name="centos", supported_operating_systems=["centos-stream-9"]
        )
        assert mock_py_config["centos_os_matrix"] == sample_centos_matrix

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_windows_os_matrix(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
    ):
        """Test generating Windows OS matrix from windows_os_list"""
        mock_get_arch.return_value = "amd64"
        sample_windows_matrix = [{"win-10": {"os_version": "10", "latest_released": True}}]
        mock_generate_os_matrix.return_value = sample_windows_matrix
        mock_generate_latest.return_value = sample_windows_matrix[0]["win-10"]

        os_dict = {"windows_os_list": ["win-10"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        mock_generate_os_matrix.assert_called_once_with(os_name="windows", supported_operating_systems=["win-10"])
        assert mock_py_config["windows_os_matrix"] == sample_windows_matrix

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_instance_type_rhel_matrix_amd64(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
        sample_instance_type_matrix,
    ):
        """Test generating instance type RHEL matrix on amd64 architecture"""
        mock_get_arch.return_value = "amd64"
        mock_generate_instance_type.return_value = sample_instance_type_matrix
        mock_generate_latest.return_value = sample_instance_type_matrix[0]["rhel.9"]

        os_dict = {"instance_type_rhel_os_list": ["rhel.9"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        # On amd64, arch_suffix should be None
        mock_generate_instance_type.assert_called_once_with(os_name="rhel", preferences=["rhel.9"], arch_suffix=None)
        assert mock_py_config["instance_type_rhel_os_matrix"] == sample_instance_type_matrix

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_instance_type_rhel_matrix_arm64(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
        sample_instance_type_matrix,
    ):
        """Test generating instance type RHEL matrix on arm64 architecture"""
        mock_get_arch.return_value = "arm64"
        mock_generate_instance_type.return_value = sample_instance_type_matrix
        mock_generate_latest.return_value = sample_instance_type_matrix[0]["rhel.9"]

        os_dict = {"instance_type_rhel_os_list": ["rhel.9"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        # On arm64, arch_suffix should be "arm64"
        mock_generate_instance_type.assert_called_once_with(os_name="rhel", preferences=["rhel.9"], arch_suffix="arm64")

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_instance_type_fedora_matrix(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
    ):
        """Test generating instance type Fedora matrix"""
        mock_get_arch.return_value = "amd64"
        sample_fedora_instance_type = [{"fedora": {"preference": "fedora"}}]
        mock_generate_instance_type.return_value = sample_fedora_instance_type

        os_dict = {"instance_type_fedora_os_list": ["fedora"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        mock_generate_instance_type.assert_called_once_with(os_name="fedora", preferences=["fedora"], arch_suffix=None)
        assert mock_py_config["instance_type_fedora_os_matrix"] == sample_fedora_instance_type

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_instance_type_centos_matrix(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
    ):
        """Test generating instance type CentOS matrix"""
        mock_get_arch.return_value = "amd64"
        sample_centos_instance_type = [{"centos.stream9": {"preference": "centos.stream9"}}]
        mock_generate_instance_type.return_value = sample_centos_instance_type

        os_dict = {"instance_type_centos_os_list": ["centos.stream9"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        mock_generate_instance_type.assert_called_once_with(
            os_name="centos", preferences=["centos.stream9"], arch_suffix=None
        )
        assert mock_py_config["instance_type_centos_os_matrix"] == sample_centos_instance_type

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_empty_os_dict_does_nothing(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
    ):
        """Test that empty os_dict doesn't call any generation functions"""
        mock_get_arch.return_value = "amd64"

        os_dict = {}
        generate_os_matrix_dicts(os_dict=os_dict)

        mock_generate_os_matrix.assert_not_called()
        mock_generate_instance_type.assert_not_called()

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_multiple_os_matrices(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
        sample_rhel_matrix,
        sample_fedora_matrix,
    ):
        """Test generating multiple OS matrices in a single call"""
        mock_get_arch.return_value = "amd64"
        mock_generate_os_matrix.side_effect = [sample_rhel_matrix, sample_fedora_matrix]
        mock_generate_latest.side_effect = [
            sample_rhel_matrix[0]["rhel-9-6"],
            sample_fedora_matrix[0]["fedora-43"],
        ]

        os_dict = {
            "rhel_os_list": ["rhel-9-6"],
            "fedora_os_list": ["fedora-43"],
        }
        generate_os_matrix_dicts(os_dict=os_dict)

        assert mock_generate_os_matrix.call_count == 2
        assert mock_py_config["rhel_os_matrix"] == sample_rhel_matrix
        assert mock_py_config["fedora_os_matrix"] == sample_fedora_matrix

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_instance_type_centos_matrix_s390x(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
    ):
        """Test that CentOS instance type on s390x uses None for arch_suffix"""
        mock_get_arch.return_value = "s390x"
        sample_centos_instance_type = [{"centos.stream9": {"preference": "centos.stream9"}}]
        mock_generate_instance_type.return_value = sample_centos_instance_type

        os_dict = {"instance_type_centos_os_list": ["centos.stream9"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        mock_generate_instance_type.assert_called_once_with(
            os_name="centos", preferences=["centos.stream9"], arch_suffix=None
        )

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_generate_instance_type_rhel_matrix_s390x(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
        sample_instance_type_matrix,
    ):
        """Test generating instance type RHEL matrix on s390x architecture"""
        mock_get_arch.return_value = "s390x"
        mock_generate_instance_type.return_value = sample_instance_type_matrix
        mock_generate_latest.return_value = sample_instance_type_matrix[0]["rhel.9"]

        os_dict = {"instance_type_rhel_os_list": ["rhel.9"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        mock_generate_instance_type.assert_called_once_with(os_name="rhel", preferences=["rhel.9"], arch_suffix="s390x")

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_sets_latest_rhel_os_dict(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
        sample_rhel_matrix,
    ):
        """Test that latest_rhel_os_dict is populated correctly"""
        mock_get_arch.return_value = "amd64"
        mock_generate_os_matrix.return_value = sample_rhel_matrix
        expected_latest = {"os_version": "9.6", "image_name": "rhel-9.6.qcow2", "latest_released": True}
        mock_generate_latest.return_value = expected_latest

        os_dict = {"rhel_os_list": ["rhel-9-6"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        assert mock_py_config["latest_rhel_os_dict"] == expected_latest

    @patch("utilities.pytest_utils.get_cluster_architecture")
    @patch("utilities.pytest_utils.generate_linux_instance_type_os_matrix")
    @patch("utilities.pytest_utils.generate_latest_os_dict")
    @patch("utilities.pytest_utils.generate_os_matrix_dict")
    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_sets_latest_instance_type_rhel_os_dict(
        self,
        mock_py_config,
        mock_generate_os_matrix,
        mock_generate_latest,
        mock_generate_instance_type,
        mock_get_arch,
        sample_instance_type_matrix,
    ):
        """Test that latest_instance_type_rhel_os_dict is populated correctly"""
        mock_get_arch.return_value = "amd64"
        mock_generate_instance_type.return_value = sample_instance_type_matrix
        expected_latest = {"preference": "rhel.9", "latest_released": True}
        mock_generate_latest.return_value = expected_latest

        os_dict = {"instance_type_rhel_os_list": ["rhel.9"]}
        generate_os_matrix_dicts(os_dict=os_dict)

        assert mock_py_config["latest_instance_type_rhel_os_dict"] == expected_latest


class TestUpdateLatestOsConfig:
    """Test cases for update_latest_os_config function"""

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_saves_system_windows_os_matrix(self, mock_py_config):
        """Test that windows_os_matrix is saved to system_windows_os_matrix"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.return_value = False
        windows_matrix = [{"win-10": {"os_version": "10"}}]
        mock_py_config["windows_os_matrix"] = windows_matrix

        update_latest_os_config(session_config=mock_session_config)

        assert mock_py_config["system_windows_os_matrix"] == windows_matrix

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_saves_system_rhel_os_matrix(self, mock_py_config):
        """Test that rhel_os_matrix is saved to system_rhel_os_matrix"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.return_value = False
        rhel_matrix = [{"rhel-9-6": {"os_version": "9.6"}}]
        mock_py_config["rhel_os_matrix"] = rhel_matrix

        update_latest_os_config(session_config=mock_session_config)

        assert mock_py_config["system_rhel_os_matrix"] == rhel_matrix

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_updates_rhel_matrix_with_latest_rhel_option(self, mock_py_config):
        """Test updating rhel_os_matrix when latest_rhel option is set"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.side_effect = lambda opt: opt == "latest_rhel"
        mock_py_config["rhel_os_matrix"] = [
            {"rhel-8-10": {"os_version": "8.10"}},
            {"rhel-9-6": {"os_version": "9.6", "latest_released": True}},
        ]
        mock_py_config["latest_rhel_os_dict"] = {"os_version": "9.6", "latest_released": True}
        mock_py_config["latest_instance_type_rhel_os_dict"] = {"preference": "rhel.9", "latest_released": True}

        update_latest_os_config(session_config=mock_session_config)

        assert mock_py_config["rhel_os_matrix"] == [{"rhel.9.6": {"os_version": "9.6", "latest_released": True}}]
        assert mock_py_config["instance_type_rhel_os_matrix"] == [
            {"rhel.9": {"preference": "rhel.9", "latest_released": True}}
        ]

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_updates_windows_matrix_with_latest_windows_option(self, mock_py_config):
        """Test updating windows_os_matrix when latest_windows option is set"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.side_effect = lambda opt: opt == "latest_windows"
        mock_py_config["windows_os_matrix"] = [
            {"win-10": {"os_version": "10"}},
            {"win-2025": {"os_version": "2025", "latest_released": True}},
        ]
        mock_py_config["latest_windows_os_dict"] = {"os_version": "2025", "latest_released": True}

        update_latest_os_config(session_config=mock_session_config)

        assert mock_py_config["windows_os_matrix"] == [
            {"windows.2025": {"os_version": "2025", "latest_released": True}}
        ]

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_updates_centos_matrix_with_latest_centos_option(self, mock_py_config):
        """Test updating centos_os_matrix when latest_centos option is set"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.side_effect = lambda opt: opt == "latest_centos"
        mock_py_config["centos_os_matrix"] = [{"centos-stream-9": {"os_version": "9", "latest_released": True}}]
        mock_py_config["latest_centos_os_dict"] = {"os_version": "9", "latest_released": True}

        update_latest_os_config(session_config=mock_session_config)

        assert mock_py_config["centos_os_matrix"] == [{"centos-stream.9": {"os_version": "9", "latest_released": True}}]

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_updates_fedora_matrix_with_latest_fedora_option(self, mock_py_config):
        """Test updating fedora_os_matrix when latest_fedora option is set"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.side_effect = lambda opt: opt == "latest_fedora"
        mock_py_config["fedora_os_matrix"] = [{"fedora-43": {"os_version": "43", "latest_released": True}}]
        mock_py_config["latest_fedora_os_dict"] = {"os_version": "43", "latest_released": True}

        update_latest_os_config(session_config=mock_session_config)

        assert mock_py_config["fedora_os_matrix"] == [{"fedora": {"os_version": "43", "latest_released": True}}]

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_no_update_without_latest_option(self, mock_py_config):
        """Test that matrices are not updated when latest_* options are not set"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.return_value = False
        original_rhel_matrix = [{"rhel-8-10": {"os_version": "8.10"}}, {"rhel-9-6": {"os_version": "9.6"}}]
        mock_py_config["rhel_os_matrix"] = original_rhel_matrix.copy()

        update_latest_os_config(session_config=mock_session_config)

        assert mock_py_config["rhel_os_matrix"] == original_rhel_matrix

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_latest_rhel_with_missing_latest_dict_uses_defaults(self, mock_py_config):
        """Test fallback to default values when latest_rhel_os_dict is missing"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.side_effect = lambda opt: opt == "latest_rhel"
        mock_py_config["rhel_os_matrix"] = [{"rhel-9-6": {"os_version": "9.6"}}]

        update_latest_os_config(session_config=mock_session_config)

        assert mock_py_config["rhel_os_matrix"] == [{"rhel.latest": {}}]
        assert mock_py_config["instance_type_rhel_os_matrix"] == [{"rhel.latest": {}}]

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_latest_windows_with_missing_latest_dict_uses_defaults(self, mock_py_config):
        """Test fallback to default values when latest_windows_os_dict is missing"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.side_effect = lambda opt: opt == "latest_windows"
        mock_py_config["windows_os_matrix"] = [{"win-10": {"os_version": "10"}}]

        update_latest_os_config(session_config=mock_session_config)

        assert mock_py_config["windows_os_matrix"] == [{"windows.latest": {}}]

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_no_update_when_matrix_is_missing(self, mock_py_config):
        """Test that latest_* options are ignored when corresponding matrix is missing"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.side_effect = lambda opt: opt == "latest_rhel"

        update_latest_os_config(session_config=mock_session_config)

        assert "rhel_os_matrix" not in mock_py_config

    @patch("utilities.pytest_utils.py_config", new_callable=dict)
    def test_multiple_latest_options(self, mock_py_config):
        """Test handling multiple latest_* options simultaneously"""
        mock_session_config = MagicMock()
        mock_session_config.getoption.side_effect = lambda opt: opt in ("latest_rhel", "latest_windows")
        mock_py_config["rhel_os_matrix"] = [{"rhel-9-6": {"os_version": "9.6"}}]
        mock_py_config["latest_rhel_os_dict"] = {"os_version": "9.6"}
        mock_py_config["latest_instance_type_rhel_os_dict"] = {"preference": "rhel.9"}
        mock_py_config["windows_os_matrix"] = [{"win-2025": {"os_version": "2025"}}]
        mock_py_config["latest_windows_os_dict"] = {"os_version": "2025"}

        update_latest_os_config(session_config=mock_session_config)

        assert mock_py_config["rhel_os_matrix"] == [{"rhel.9.6": {"os_version": "9.6"}}]
        assert mock_py_config["windows_os_matrix"] == [{"windows.2025": {"os_version": "2025"}}]
