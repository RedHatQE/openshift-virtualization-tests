"""Unit tests for must_gather module"""

import os
import tempfile
from unittest.mock import mock_open, patch

import pytest

from utilities.must_gather import (
    collect_must_gather,
    get_must_gather_output_dir,
    get_must_gather_output_file,
    run_must_gather,
)


class TestRunMustGather:
    """Test cases for run_must_gather function"""

    @patch("utilities.must_gather.run_command")
    def test_run_must_gather_minimal(self, mock_run_command):
        """Test run_must_gather with minimal parameters"""
        mock_run_command.return_value = (True, "success output", "")

        result = run_must_gather()

        expected_command = ["oc", "adm", "must-gather", "--timeout=900s"]
        mock_run_command.assert_called_once_with(
            command=expected_command,
            check=False,
            timeout=1200,
            log_errors=False,
        )
        assert result == "success output"

    @patch("utilities.must_gather.run_command")
    def test_run_must_gather_all_parameters(self, mock_run_command):
        """Test run_must_gather with all parameters"""
        mock_run_command.return_value = (True, "success output", "")

        result = run_must_gather(
            image_url="quay.io/test/image",
            target_base_dir="/tmp/test",
            script_name="/usr/bin/gather",
            node_name="test-node",
            flag_names="default,logs",
            timeout="1800s",
            since="1h",
        )

        expected_command = [
            "oc",
            "adm",
            "must-gather",
            "--dest-dir=/tmp/test",
            "--image=quay.io/test/image",
            "--node-name=test-node",
            "--since=1h",
            "--timeout=1800s",
            "--",
            "/usr/bin/gather",
            "--default",
            "--logs",
        ]
        mock_run_command.assert_called_once_with(
            command=expected_command,
            check=False,
            timeout=1200,
            log_errors=False,
        )
        assert result == "success output"

    @patch("utilities.must_gather.run_command")
    @patch("utilities.must_gather.LOGGER")
    def test_run_must_gather_with_warning(self, mock_logger, mock_run_command):
        """Test run_must_gather with warning in error output"""
        mock_run_command.return_value = (False, "output", "Warning: something happened")

        result = run_must_gather()

        mock_logger.warning.assert_called_once_with(
            "must-gather raised the following error: Warning: something happened",
        )
        assert result == "output"

    @patch("utilities.must_gather.run_command")
    @patch("utilities.must_gather.LOGGER")
    def test_run_must_gather_with_error(self, mock_logger, mock_run_command):
        """Test run_must_gather with error in error output"""
        mock_run_command.return_value = (False, "output", "Error: something failed")

        result = run_must_gather()

        mock_logger.error.assert_called_once_with(
            "must-gather raised the following error: Error: something failed",
        )
        assert result == "output"

    @patch("utilities.must_gather.run_command")
    def test_run_must_gather_success_no_error_logging(self, mock_run_command):
        """Test run_must_gather success case with no error logging"""
        mock_run_command.return_value = (True, "success output", "")

        with patch("utilities.must_gather.LOGGER") as mock_logger:
            result = run_must_gather()

            mock_logger.warning.assert_not_called()
            mock_logger.error.assert_not_called()
            assert result == "success output"


class TestGetMustGatherOutputFile:
    """Test cases for get_must_gather_output_file function"""

    def test_get_must_gather_output_file(self):
        """Test get_must_gather_output_file returns correct path"""
        input_path = "/tmp/test/subdir"
        result = get_must_gather_output_file(input_path)
        expected = "/tmp/test/subdir/../output.log"
        assert result == expected

    def test_get_must_gather_output_file_root_path(self):
        """Test get_must_gather_output_file with root-level path"""
        input_path = "/subdir"
        result = get_must_gather_output_file(input_path)
        expected = "/subdir/../output.log"
        assert result == expected


class TestGetMustGatherOutputDir:
    """Test cases for get_must_gather_output_dir function"""

    def test_get_must_gather_output_dir_success(self):
        """Test get_must_gather_output_dir finds directory successfully"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a subdirectory
            sub_dir = os.path.join(tmp_dir, "must-gather-123")
            os.makedirs(sub_dir)

            result = get_must_gather_output_dir(tmp_dir)
            assert result == sub_dir

    def test_get_must_gather_output_dir_multiple_dirs(self):
        """Test get_must_gather_output_dir with multiple directories"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create multiple subdirectories
            sub_dir1 = os.path.join(tmp_dir, "must-gather-123")
            sub_dir2 = os.path.join(tmp_dir, "must-gather-456")
            os.makedirs(sub_dir1)
            os.makedirs(sub_dir2)

            result = get_must_gather_output_dir(tmp_dir)
            # Should return the first directory found
            assert result in [sub_dir1, sub_dir2]

    def test_get_must_gather_output_dir_no_dirs(self):
        """Test get_must_gather_output_dir with no directories"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create only files, no directories
            test_file = os.path.join(tmp_dir, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")

            with pytest.raises(FileNotFoundError) as exc_info:
                get_must_gather_output_dir(tmp_dir)

            assert f"No log directory was created in '{tmp_dir}'" in str(exc_info.value)

    def test_get_must_gather_output_dir_mixed_files_and_dirs(self):
        """Test get_must_gather_output_dir with mixed files and directories"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create files and a directory
            test_file = os.path.join(tmp_dir, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")

            sub_dir = os.path.join(tmp_dir, "must-gather-123")
            os.makedirs(sub_dir)

            result = get_must_gather_output_dir(tmp_dir)
            assert result == sub_dir


class TestCollectMustGather:
    """Test cases for collect_must_gather function"""

    @patch("utilities.must_gather.run_must_gather")
    @patch("utilities.must_gather.get_must_gather_output_dir")
    @patch("builtins.open", new_callable=mock_open)
    def test_collect_must_gather_minimal(self, mock_file_open, mock_get_output_dir, mock_run_must_gather):
        """Test collect_must_gather with minimal parameters"""
        mock_run_must_gather.return_value = "must gather output"
        mock_get_output_dir.return_value = "/tmp/test/output-dir"

        result = collect_must_gather("/tmp/test", "quay.io/test/image")

        mock_run_must_gather.assert_called_once_with(
            image_url="quay.io/test/image",
            target_base_dir="/tmp/test",
            script_name="/usr/bin/gather",
            node_name="",
            flag_names="",
            timeout="",
            command_timeout=1200,
        )
        mock_file_open.assert_called_once_with("/tmp/test/output.log", "w")
        mock_file_open().write.assert_called_once_with("must gather output")
        mock_get_output_dir.assert_called_once_with(must_gather_path="/tmp/test")
        assert result == "/tmp/test/output-dir"

    @patch("utilities.must_gather.run_must_gather")
    @patch("utilities.must_gather.get_must_gather_output_dir")
    @patch("builtins.open", new_callable=mock_open)
    def test_collect_must_gather_all_parameters(self, mock_file_open, mock_get_output_dir, mock_run_must_gather):
        """Test collect_must_gather with all parameters"""
        mock_run_must_gather.return_value = "must gather output"
        mock_get_output_dir.return_value = "/tmp/test/output-dir"

        result = collect_must_gather(
            "/tmp/test",
            "quay.io/test/image",
            script_name="/usr/bin/custom-gather",
            flag_names="default,logs",
            timeout="1800s",
            node_name="test-node",
        )

        mock_run_must_gather.assert_called_once_with(
            image_url="quay.io/test/image",
            target_base_dir="/tmp/test",
            script_name="/usr/bin/custom-gather",
            node_name="test-node",
            flag_names="default,logs",
            timeout="1800s",
            command_timeout=1200,
        )
        assert result == "/tmp/test/output-dir"

    @patch("utilities.must_gather.run_must_gather")
    @patch("utilities.must_gather.get_must_gather_output_dir")
    @patch("builtins.open", new_callable=mock_open)
    def test_collect_must_gather_file_write_error(self, mock_file_open, mock_get_output_dir, mock_run_must_gather):
        """Test collect_must_gather when file write fails"""
        mock_run_must_gather.return_value = "must gather output"
        mock_file_open.side_effect = OSError("Cannot write file")

        with pytest.raises(OSError, match="Cannot write file"):
            collect_must_gather("/tmp/test", "quay.io/test/image")
