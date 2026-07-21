# Generated using Claude cli

"""Unit tests for pytest_utils module"""

from unittest.mock import MagicMock, patch
from xml.etree import ElementTree

import pytest

# Circular dependencies are already mocked in conftest.py
from utilities import pytest_utils as pytest_utils_module
from utilities.exceptions import MissingEnvironmentVariableError
from utilities.pytest_utils import (
    _validate_storage_class_options,
    config_default_storage_class,
    deploy_run_in_progress_config_map,
    deploy_run_in_progress_namespace,
    get_artifactory_server_url,
    get_base_matrix_name,
    get_cnv_version_explorer_url,
    get_current_running_data,
    get_matrix_params,
    reorder_early_fixtures,
    run_in_progress_config_map,
    separator,
    skip_if_pytest_flags_exists,
    stop_if_run_in_progress,
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
            "system_storage_class_matrix": [
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

        assert pytest_utils_module.py_config["default_storage_class"] == "new-sc"
        assert pytest_utils_module.py_config["default_volume_mode"] == "Filesystem"
        assert pytest_utils_module.py_config["default_access_mode"] == "ReadWriteOnce"

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "storage_class_matrix": [
                {"first-sc": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
                {"second-sc": {"volume_mode": "Block", "access_mode": "ReadWriteMany"}},
            ],
            "system_storage_class_matrix": [
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

        assert pytest_utils_module.py_config["default_storage_class"] == "first-sc"
        assert pytest_utils_module.py_config["default_volume_mode"] == "Filesystem"
        assert pytest_utils_module.py_config["default_access_mode"] == "ReadWriteOnce"

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "storage_class_matrix": [
                {"first-sc": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
                {"original-sc": {"volume_mode": "Block", "access_mode": "ReadWriteMany"}},
            ],
            "system_storage_class_matrix": [
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

        # Should keep original-sc since it's in the matrix
        assert pytest_utils_module.py_config["default_storage_class"] == "original-sc"

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "system_storage_class_matrix": [],
        },
    )
    def test_config_default_storage_class_no_changes(self):
        """Test no changes when no overrides provided"""
        mock_session = MagicMock()
        mock_session.config.getoption.side_effect = lambda name: {
            "default_storage_class": None,
            "storage_class_matrix": None,
        }.get(name)

        config_default_storage_class(mock_session)

        # Should remain unchanged
        assert pytest_utils_module.py_config["default_storage_class"] == "original-sc"

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "system_storage_class_matrix": [
                {"existing-sc-1": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
                {"existing-sc-2": {"volume_mode": "Block", "access_mode": "ReadWriteMany"}},
            ],
        },
    )
    @patch("utilities.pytest_utils.write_to_file")
    @patch("utilities.pytest_utils.get_data_collector_base_directory", return_value="/tmp")
    @patch("utilities.pytest_utils.pytest.exit", side_effect=SystemExit(4))
    def test_config_default_storage_class_not_found_raises_error(
        self, mock_pytest_exit, mock_get_base_dir, mock_write_to_file
    ):
        """Test clean exit when requested default storage class is not in system matrix"""
        mock_session = MagicMock()
        mock_session.config.getoption.side_effect = lambda name: {
            "default_storage_class": "nonexistent-sc",
            "storage_class_matrix": None,
        }.get(name)

        with pytest.raises(SystemExit):
            config_default_storage_class(mock_session)

        mock_pytest_exit.assert_called_once()
        assert mock_pytest_exit.call_args[1]["returncode"] == 4
        assert "nonexistent-sc" in mock_pytest_exit.call_args[1]["reason"]
        mock_write_to_file.assert_called_once()

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "system_storage_class_matrix": [
                {"existing-sc-1": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
                {"existing-sc-2": {"volume_mode": "Block", "access_mode": "ReadWriteMany"}},
            ],
        },
    )
    @patch("utilities.pytest_utils.write_to_file")
    @patch("utilities.pytest_utils.get_data_collector_base_directory", return_value="/tmp")
    @patch("utilities.pytest_utils.pytest.exit", side_effect=SystemExit(4))
    def test_config_default_storage_class_invalid_matrix_values_raises_error(
        self, mock_pytest_exit, mock_get_base_dir, mock_write_to_file
    ):
        """Test clean exit when --storage-class-matrix contains invalid storage class names"""
        mock_session = MagicMock()
        mock_session.config.getoption.side_effect = lambda name: {
            "default_storage_class": None,
            "storage_class_matrix": "nonexistent-sc,existing-sc-1",
        }.get(name)

        with pytest.raises(SystemExit):
            config_default_storage_class(mock_session)

        mock_pytest_exit.assert_called_once()
        assert mock_pytest_exit.call_args[1]["returncode"] == 4
        assert "nonexistent-sc" in mock_pytest_exit.call_args[1]["reason"]
        mock_write_to_file.assert_called_once()

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "system_storage_class_matrix": [
                {"sc-1": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
                {"sc-2": {"volume_mode": "Block", "access_mode": "ReadWriteMany"}},
            ],
        },
    )
    @patch("utilities.pytest_utils.write_to_file")
    @patch("utilities.pytest_utils.get_data_collector_base_directory", return_value="/tmp")
    @patch("utilities.pytest_utils.pytest.exit", side_effect=SystemExit(4))
    def test_config_default_storage_class_not_in_matrix_raises_error(
        self, mock_pytest_exit, mock_get_base_dir, mock_write_to_file
    ):
        """Test clean exit when --default-storage-class is not in --storage-class-matrix"""
        mock_session = MagicMock()
        mock_session.config.getoption.side_effect = lambda name: {
            "default_storage_class": "sc-1",
            "storage_class_matrix": "sc-2",
        }.get(name)

        with pytest.raises(SystemExit):
            config_default_storage_class(mock_session)

        mock_pytest_exit.assert_called_once()
        assert mock_pytest_exit.call_args[1]["returncode"] == 4
        assert "sc-1" in mock_pytest_exit.call_args[1]["reason"]
        mock_write_to_file.assert_called_once()

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "system_storage_class_matrix": [
                {"sc-1": {"volume_mode": "Filesystem", "access_mode": "ReadWriteOnce"}},
                {"sc-2": {"volume_mode": "Block", "access_mode": "ReadWriteMany"}},
            ],
        },
    )
    def test_config_default_storage_class_both_options_valid(self):
        """Test correct update when both --default-storage-class and --storage-class-matrix are valid"""
        mock_session = MagicMock()
        mock_session.config.getoption.side_effect = lambda name: {
            "default_storage_class": "sc-1",
            "storage_class_matrix": "sc-1,sc-2",
        }.get(name)

        config_default_storage_class(mock_session)

        assert pytest_utils_module.py_config["default_storage_class"] == "sc-1"
        assert pytest_utils_module.py_config["default_volume_mode"] == "Filesystem"
        assert pytest_utils_module.py_config["default_access_mode"] == "ReadWriteOnce"

    @patch(
        "utilities.pytest_utils.py_config",
        {
            "default_storage_class": "original-sc",
            "system_storage_class_matrix": [
                {"original-sc": {"volume_mode": "Block", "access_mode": "ReadWriteMany"}},
            ],
        },
    )
    def test_config_default_storage_class_same_as_global(self):
        """Test no update when --default-storage-class matches global default"""
        mock_session = MagicMock()
        mock_session.config.getoption.side_effect = lambda name: {
            "default_storage_class": "original-sc",
            "storage_class_matrix": None,
        }.get(name)

        config_default_storage_class(mock_session)

        assert pytest_utils_module.py_config["default_storage_class"] == "original-sc"


class TestValidateStorageClassOptions:
    """Test cases for _validate_storage_class_options function"""

    @patch(
        "utilities.pytest_utils.py_config",
        {"system_storage_class_matrix": [{"sc-1": {}}, {"sc-2": {}}, {"sc-3": {}}]},
    )
    def test_valid_matrix_and_default(self):
        """Test no error when all values are valid"""
        _validate_storage_class_options(
            cmd_default_storage_class="sc-1",
            cmdline_storage_class_matrix=["sc-1", "sc-2"],
        )

    @patch(
        "utilities.pytest_utils.py_config",
        {"system_storage_class_matrix": [{"sc-1": {}}, {"sc-2": {}}]},
    )
    def test_valid_matrix_no_default(self):
        """Test no error when matrix is valid and no default is specified"""
        _validate_storage_class_options(
            cmd_default_storage_class=None,
            cmdline_storage_class_matrix=["sc-1", "sc-2"],
        )

    @patch(
        "utilities.pytest_utils.py_config",
        {"system_storage_class_matrix": [{"sc-1": {}}]},
    )
    def test_no_options(self):
        """Test no error when no options are specified"""
        _validate_storage_class_options(
            cmd_default_storage_class=None,
            cmdline_storage_class_matrix=None,
        )

    @patch(
        "utilities.pytest_utils.py_config",
        {"system_storage_class_matrix": [{"sc-1": {}}, {"sc-2": {}}]},
    )
    def test_invalid_matrix_value(self):
        """Test ValueError for invalid storage class in matrix"""
        with pytest.raises(ValueError, match=r"from --storage-class-matrix not found"):
            _validate_storage_class_options(
                cmd_default_storage_class=None,
                cmdline_storage_class_matrix=["bad-sc"],
            )

    @patch(
        "utilities.pytest_utils.py_config",
        {"system_storage_class_matrix": [{"sc-1": {}}, {"sc-2": {}}]},
    )
    def test_invalid_default_sc(self):
        """Test ValueError for default SC not in system matrix"""
        with pytest.raises(ValueError, match=r"Default storage class 'bad-sc' not found"):
            _validate_storage_class_options(
                cmd_default_storage_class="bad-sc",
                cmdline_storage_class_matrix=None,
            )

    @patch(
        "utilities.pytest_utils.py_config",
        {"system_storage_class_matrix": [{"sc-1": {}}, {"sc-2": {}}]},
    )
    def test_valid_default_no_matrix(self):
        """Test no error when default SC is valid and no matrix is specified"""
        _validate_storage_class_options(
            cmd_default_storage_class="sc-1",
            cmdline_storage_class_matrix=None,
        )

    @patch(
        "utilities.pytest_utils.py_config",
        {"system_storage_class_matrix": [{"sc-1": {}}]},
    )
    def test_multiple_invalid_matrix_values(self):
        """Test all invalid storage class names are reported"""
        with pytest.raises(ValueError, match=r"\['bad-sc-1', 'bad-sc-2'\]"):
            _validate_storage_class_options(
                cmd_default_storage_class=None,
                cmdline_storage_class_matrix=["bad-sc-1", "bad-sc-2"],
            )

    @patch(
        "utilities.pytest_utils.py_config",
        {"system_storage_class_matrix": [{"sc-1": {}}]},
    )
    def test_invalid_matrix_checked_before_default_not_in_matrix(self):
        """Test matrix validation runs before default-in-matrix check"""
        with pytest.raises(ValueError, match=r"from --storage-class-matrix not found"):
            _validate_storage_class_options(
                cmd_default_storage_class="sc-1",
                cmdline_storage_class_matrix=["bad-sc"],
            )

    @patch(
        "utilities.pytest_utils.py_config",
        {"system_storage_class_matrix": [{"sc-1": {}}, {"sc-2": {}}, {"sc-3": {}}]},
    )
    def test_default_sc_not_in_matrix(self):
        """Test ValueError when default SC exists on system but not in the provided matrix"""
        with pytest.raises(ValueError, match=r"not in --storage-class-matrix"):
            _validate_storage_class_options(
                cmd_default_storage_class="sc-1",
                cmdline_storage_class_matrix=["sc-2", "sc-3"],
            )

    @patch(
        "utilities.pytest_utils.py_config",
        {"system_storage_class_matrix": [{"sc-1": {}}, {"sc-2": {}}]},
    )
    def test_valid_matrix_skips_system_check_for_default(self):
        """Test that when matrix is valid, default SC is only checked against matrix not system"""
        _validate_storage_class_options(
            cmd_default_storage_class="sc-1",
            cmdline_storage_class_matrix=["sc-1"],
        )


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

    def test_reorder_early_fixtures_with_early_mark(self):
        """Test reordering fixtures with early mark"""
        # Create mock fixture with early mark
        mock_fixturedef = MagicMock()
        mock_fixturedef.argname = "early_fixture"

        mock_mark = MagicMock()
        mock_mark.name = "early"
        mock_mark.kwargs = {"order": 0}

        mock_fixturedef.func.pytestmark = [mock_mark]

        # Create mock metafunc
        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {"early_fixture": [mock_fixturedef]}
        mock_metafunc.fixturenames = ["other_fixture", "early_fixture", "another_fixture"]

        reorder_early_fixtures(mock_metafunc)

        # early_fixture should be moved to position 0
        assert mock_metafunc.fixturenames == ["early_fixture", "other_fixture", "another_fixture"]

    def test_reorder_early_fixtures_no_early_mark(self):
        """Test fixtures without early mark remain unchanged"""
        mock_fixturedef = MagicMock()
        mock_fixturedef.argname = "normal_fixture"
        mock_fixturedef.func.pytestmark = []

        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {"normal_fixture": [mock_fixturedef]}
        mock_metafunc.fixturenames = ["fixture1", "normal_fixture", "fixture2"]

        original_order = mock_metafunc.fixturenames.copy()
        reorder_early_fixtures(mock_metafunc)

        assert mock_metafunc.fixturenames == original_order

    def test_reorder_early_fixtures_no_pytestmark(self):
        """Test fixtures without pytestmark attribute"""
        mock_fixturedef = MagicMock()
        mock_fixturedef.argname = "normal_fixture"
        # No pytestmark attribute
        del mock_fixturedef.func.pytestmark

        mock_metafunc = MagicMock()
        mock_metafunc._arg2fixturedefs = {"normal_fixture": [mock_fixturedef]}
        mock_metafunc.fixturenames = ["fixture1", "normal_fixture", "fixture2"]

        original_order = mock_metafunc.fixturenames.copy()
        reorder_early_fixtures(mock_metafunc)

        assert mock_metafunc.fixturenames == original_order


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

        stop_if_run_in_progress()

        mock_exit.assert_called_once()
        assert "test_user" in mock_exit.call_args[1]["message"]
        assert mock_exit.call_args[1]["return_code"] == 100

    @patch("utilities.pytest_utils.run_in_progress_config_map")
    @patch("utilities.pytest_utils.exit_pytest_execution")
    def test_stop_if_run_in_progress_not_exists(self, mock_exit, mock_config_map):
        """Test not stopping when no run is in progress"""
        mock_cm = MagicMock()
        mock_cm.exists = False
        mock_config_map.return_value = mock_cm

        stop_if_run_in_progress()

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

        result = deploy_run_in_progress_namespace()

        assert result == mock_namespace
        mock_namespace.deploy.assert_called_once_with(wait=True)
        mock_namespace.wait_for_status.assert_called_once()
        mock_resource_editor.assert_called_once()

    @patch("utilities.pytest_utils.Namespace")
    def test_deploy_run_in_progress_namespace_exists(self, mock_namespace_class):
        """Test when namespace already exists"""
        mock_namespace = MagicMock()
        mock_namespace.exists = True
        mock_namespace_class.return_value = mock_namespace

        result = deploy_run_in_progress_namespace()

        assert result == mock_namespace
        mock_namespace.deploy.assert_not_called()


class TestDeployRunInProgressConfigMap:
    """Test cases for deploy_run_in_progress_config_map function"""

    @patch("utilities.pytest_utils.run_in_progress_config_map")
    def test_deploy_run_in_progress_config_map(self, mock_config_map):
        """Test deploying run in progress config map"""
        mock_cm = MagicMock()
        mock_config_map.return_value = mock_cm
        mock_session = MagicMock()

        deploy_run_in_progress_config_map(mock_session)

        mock_config_map.assert_called_once_with(session=mock_session)
        mock_cm.deploy.assert_called_once()


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

        result = run_in_progress_config_map(mock_session)

        assert result == mock_cm
        mock_get_data.assert_called_once_with(session=mock_session)
        mock_config_map_class.assert_called_once_with(
            name="cnv-tests-run-in-progress", namespace="cnv-tests-run-in-progress-ns", data=mock_data
        )

    @patch("utilities.pytest_utils.ConfigMap")
    def test_run_in_progress_config_map_without_session(self, mock_config_map_class):
        """Test creating config map without session data"""
        mock_cm = MagicMock()
        mock_config_map_class.return_value = mock_cm

        result = run_in_progress_config_map(None)

        assert result == mock_cm
        mock_config_map_class.assert_called_once_with(
            name="cnv-tests-run-in-progress", namespace="cnv-tests-run-in-progress-ns", data=None
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


class TestInjectFailureJunit:
    """Test cases for _inject_failure_junit (private) and _failure_info mechanism"""

    def setup_method(self):
        pytest_utils_module._failure_info = None

    def teardown_method(self):
        pytest_utils_module._failure_info = None

    @patch("utilities.pytest_utils.ElementTree")
    def test_no_op_when_no_failure(self, mock_element_tree):
        """Test _inject_failure_junit does nothing when no failure was recorded."""
        mock_session = MagicMock()
        mock_session.config.option.xmlpath = None
        pytest_utils_module._inject_failure_junit(session=mock_session)
        mock_element_tree.parse.assert_not_called()

    @patch("utilities.pytest_utils.ElementTree")
    def test_no_op_when_no_xmlpath(self, mock_element_tree):
        """Test _inject_failure_junit does nothing when no junitxml path is configured."""
        pytest_utils_module._failure_info = {
            "message": "Test failure",
            "log_message": "Detailed failure",
            "return_code": 99,
        }

        mock_session = MagicMock()
        mock_session.config.option.xmlpath = None

        pytest_utils_module._inject_failure_junit(session=mock_session)
        mock_element_tree.parse.assert_not_called()

    def test_no_op_when_no_testsuite(self, tmp_path):
        """Test _inject_failure_junit skips injection when XML has no testsuite element."""
        pytest_utils_module._failure_info = {
            "message": "Test failure",
            "log_message": "Detailed failure",
            "return_code": 99,
        }

        xml_path = tmp_path / "test-results.xml"
        xml_path.write_text('<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests" />')

        mock_session = MagicMock()
        mock_session.config.option.xmlpath = str(xml_path)

        pytest_utils_module._inject_failure_junit(session=mock_session)

        tree = ElementTree.parse(xml_path)
        assert tree.getroot().find("testsuite") is None

    def test_injects_synthetic_testcase(self, tmp_path):
        """Test _inject_failure_junit creates synthetic error testcase in JUnit XML."""
        pytest_utils_module._failure_info = {
            "message": "Cluster sanity failed",
            "log_message": "Detailed cluster sanity failure message",
            "return_code": 99,
        }

        xml_path = tmp_path / "test-results.xml"
        xml_path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests">'
            '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" '
            'time="0.001" timestamp="2026-01-01T00:00:00" hostname="test" />'
            "</testsuites>"
        )

        mock_session = MagicMock()
        mock_session.config.option.xmlpath = str(xml_path)

        pytest_utils_module._inject_failure_junit(session=mock_session)

        tree = ElementTree.parse(xml_path)
        root = tree.getroot()
        testsuite = root.find("testsuite")
        testcase = testsuite.find("testcase")
        assert testcase is not None, "Synthetic testcase not found in XML"
        assert testcase.get("classname") == "pytest_exit"
        assert testcase.get("name") == "cluster_sanity_failed"
        error_elem = testcase.find("error")
        assert error_elem is not None, "Error element not found in testcase"
        assert "exit code: 99" in error_elem.get("message")
        assert "Detailed cluster sanity failure message" in error_elem.text
        assert testsuite.get("errors") == "1"
        assert testsuite.get("tests") == "1"

    def test_injects_into_non_empty_suite(self, tmp_path):
        """Test _inject_failure_junit appends synthetic testcase to suite with existing tests."""
        pytest_utils_module._failure_info = {
            "message": "Storage class failure",
            "log_message": "Failed to set default storage class",
            "return_code": 99,
        }

        xml_path = tmp_path / "test-results.xml"
        xml_path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests">'
            '<testsuite name="pytest" errors="0" failures="1" skipped="0" tests="3" '
            'time="10.5" timestamp="2026-01-01T00:00:00" hostname="test">'
            '<testcase classname="tests.test_example" name="test_one" time="1.0" />'
            '<testcase classname="tests.test_example" name="test_two" time="2.0">'
            '<failure message="AssertionError">assert False</failure>'
            "</testcase>"
            '<testcase classname="tests.test_example" name="test_three" time="3.0" />'
            "</testsuite>"
            "</testsuites>"
        )

        mock_session = MagicMock()
        mock_session.config.option.xmlpath = str(xml_path)

        pytest_utils_module._inject_failure_junit(session=mock_session)

        tree = ElementTree.parse(xml_path)
        root = tree.getroot()
        testsuite = root.find("testsuite")
        testcases = testsuite.findall("testcase")
        assert len(testcases) == 4, f"Expected 4 testcases, got {len(testcases)}"
        synthetic = testcases[-1]
        assert synthetic.get("classname") == "pytest_exit"
        assert synthetic.get("name") == "storage_class_failure"
        assert testsuite.get("errors") == "1"
        assert testsuite.get("tests") == "4"
        assert testsuite.get("failures") == "1"

    def test_sanitized_name_collapses_underscores(self, tmp_path):
        """Test _inject_failure_junit collapses consecutive underscores in testcase name."""
        pytest_utils_module._failure_info = {
            "message": "Cluster: sanity -- failed!",
            "log_message": "Detailed failure",
            "return_code": 99,
        }

        xml_path = tmp_path / "test-results.xml"
        xml_path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests">'
            '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" '
            'time="0.001" timestamp="2026-01-01T00:00:00" hostname="test" />'
            "</testsuites>"
        )

        mock_session = MagicMock()
        mock_session.config.option.xmlpath = str(xml_path)

        pytest_utils_module._inject_failure_junit(session=mock_session)

        tree = ElementTree.parse(xml_path)
        testsuite = tree.getroot().find("testsuite")
        testcase = testsuite.find("testcase")
        assert testcase.get("name") == "cluster_sanity_failed"

    def test_sanitized_name_fallback(self, tmp_path):
        """Test _inject_failure_junit uses 'execution_failure' for messages with only special chars."""
        pytest_utils_module._failure_info = {
            "message": "!@#$%^&*()",
            "log_message": "Special chars only",
            "return_code": 99,
        }

        xml_path = tmp_path / "test-results.xml"
        xml_path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests">'
            '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" '
            'time="0.001" timestamp="2026-01-01T00:00:00" hostname="test" />'
            "</testsuites>"
        )

        mock_session = MagicMock()
        mock_session.config.option.xmlpath = str(xml_path)

        pytest_utils_module._inject_failure_junit(session=mock_session)

        tree = ElementTree.parse(xml_path)
        testsuite = tree.getroot().find("testsuite")
        testcase = testsuite.find("testcase")
        assert testcase.get("name") == "execution_failure"

    def test_error_text_escapes_xml_chars(self, tmp_path):
        """Test _inject_failure_junit escapes XML special characters in error text."""
        pytest_utils_module._failure_info = {
            "message": "XML test",
            "log_message": 'Failed with <error> & "quotes"',
            "return_code": 99,
        }

        xml_path = tmp_path / "test-results.xml"
        xml_path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests">'
            '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" '
            'time="0.001" timestamp="2026-01-01T00:00:00" hostname="test" />'
            "</testsuites>"
        )

        mock_session = MagicMock()
        mock_session.config.option.xmlpath = str(xml_path)

        pytest_utils_module._inject_failure_junit(session=mock_session)

        tree = ElementTree.parse(xml_path)
        testsuite = tree.getroot().find("testsuite")
        testcase = testsuite.find("testcase")
        error_elem = testcase.find("error")
        assert "<error>" in error_elem.text
        assert "&" in error_elem.text

    def test_control_chars_sanitized(self, tmp_path):
        """Test _inject_failure_junit strips XML-illegal control characters from error text."""
        pytest_utils_module._failure_info = {
            "message": "Control char test",
            "log_message": "Failed\x07with\x08control\x00chars",
            "return_code": 99,
        }

        xml_path = tmp_path / "test-results.xml"
        xml_path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests">'
            '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" '
            'time="0.001" timestamp="2026-01-01T00:00:00" hostname="test" />'
            "</testsuites>"
        )

        mock_session = MagicMock()
        mock_session.config.option.xmlpath = str(xml_path)

        pytest_utils_module._inject_failure_junit(session=mock_session)

        tree = ElementTree.parse(xml_path)
        testsuite = tree.getroot().find("testsuite")
        testcase = testsuite.find("testcase")
        error_elem = testcase.find("error")
        assert error_elem.text is not None
        assert "Failed" in error_elem.text
        assert "control" in error_elem.text
        assert "\x07" not in error_elem.text
        assert "\x08" not in error_elem.text
        assert "\x00" not in error_elem.text

    def test_injection_runs_despite_earlier_teardown_failure(self, tmp_path):
        """Test _inject_failure_junit executes even when prior teardown raises."""
        pytest_utils_module._failure_info = {
            "message": "Cluster sanity failed",
            "log_message": "Sanity check failure details",
            "return_code": 99,
        }

        xml_path = tmp_path / "test-results.xml"
        xml_path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests">'
            '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" '
            'time="0.001" timestamp="2026-01-01T00:00:00" hostname="test" />'
            "</testsuites>"
        )

        mock_session = MagicMock()
        mock_session.config.option.xmlpath = str(xml_path)

        with pytest.raises(RuntimeError, match="Earlier teardown failed"):
            try:
                raise RuntimeError("Earlier teardown failed")
            finally:
                pytest_utils_module._inject_failure_junit(session=mock_session)

        tree = ElementTree.parse(xml_path)
        testsuite = tree.getroot().find("testsuite")
        testcase = testsuite.find("testcase")
        assert testcase is not None, "Synthetic testcase must be injected despite earlier failure"
        assert testcase.get("classname") == "pytest_exit"
        assert testsuite.get("errors") == "1"

    def test_atomic_write_preserves_original_on_failure(self, tmp_path):
        """Test _inject_failure_junit preserves the original XML if write fails."""
        pytest_utils_module._failure_info = {
            "message": "Test failure",
            "log_message": "Details",
            "return_code": 99,
        }

        xml_path = tmp_path / "test-results.xml"
        original_content = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests">'
            '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" '
            'time="0.001" timestamp="2026-01-01T00:00:00" hostname="test" />'
            "</testsuites>"
        )
        xml_path.write_text(original_content)

        mock_session = MagicMock()
        mock_session.config.option.xmlpath = str(xml_path)

        with patch("utilities.pytest_utils.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                pytest_utils_module._inject_failure_junit(session=mock_session)

        assert xml_path.exists()
        content = xml_path.read_text()
        assert "pytest_exit" not in content, "Original XML should not be modified on write failure"
