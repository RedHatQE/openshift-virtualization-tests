# Generated using Claude cli

"""Unit tests for bitwarden module"""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from bitwarden import (
    get_all_cnv_tests_secrets,
    get_cnv_tests_secret_by_name,
)

from utilities.exceptions import MissingEnvironmentVariableError


class TestGetAllCnvTestsSecrets:
    """Test cases for get_all_cnv_tests_secrets function"""

    @patch("bitwarden.run_command")
    def test_get_all_cnv_tests_secrets(self, mock_run_command):
        """Test getting all CNV test secrets"""
        with patch.dict(os.environ, {"ACCESS_TOKEN": "test-token"}):
            # Clear cache before test
            get_all_cnv_tests_secrets.cache_clear()

            # Mock run_command response (returns tuple: success, stdout, stderr)
            mock_run_command.return_value = (
                True,
                json.dumps([
                    {"key": "test-secret-1", "id": "uuid-1"},
                    {"key": "test-secret-2", "id": "uuid-2"},
                ]),
                "",
            )

            result = get_all_cnv_tests_secrets()

            assert len(result) == 2
            assert result == {"test-secret-1": "uuid-1", "test-secret-2": "uuid-2"}
            # Verify run_command was called correctly
            assert mock_run_command.call_count == 1
            call_args = mock_run_command.call_args
            assert call_args.kwargs["command"] == ["bws", "--access-token", "test-token", "secret", "list"]
            assert call_args.kwargs["capture_output"] is True
            assert call_args.kwargs["check"] is True

    @patch("bitwarden.run_command")
    def test_get_all_cnv_tests_secrets_command_error(self, mock_run_command):
        """Test bws command error handling for get_all_cnv_tests_secrets"""
        with patch.dict(os.environ, {"ACCESS_TOKEN": "test-token"}):
            # Clear cache before test
            get_all_cnv_tests_secrets.cache_clear()

            # Mock bws command failure (run_command raises CalledProcessError when check=True)
            mock_run_command.side_effect = subprocess.CalledProcessError(1, "bws", stderr="Authentication failed")

            with pytest.raises(subprocess.CalledProcessError):
                get_all_cnv_tests_secrets()

    @patch("bitwarden.run_command")
    def test_get_all_cnv_tests_secrets_invalid_json(self, mock_run_command):
        """Test invalid JSON handling for get_all_cnv_tests_secrets"""
        with patch.dict(os.environ, {"ACCESS_TOKEN": "test-token"}):
            # Clear cache before test
            get_all_cnv_tests_secrets.cache_clear()

            # Mock run_command with invalid JSON response
            mock_run_command.return_value = (True, "invalid json {", "")

            with pytest.raises(json.JSONDecodeError):
                get_all_cnv_tests_secrets()

    def test_get_all_cnv_tests_secrets_missing_access_token(self):
        """Test error when ACCESS_TOKEN is not set"""
        with patch.dict(os.environ, {}, clear=True):
            # Clear cache before test
            get_all_cnv_tests_secrets.cache_clear()

            with pytest.raises(
                MissingEnvironmentVariableError,
                match="Bitwarden client needs ACCESS_TOKEN environment variable set up",
            ):
                get_all_cnv_tests_secrets()


class TestGetCnvTestsSecretByName:
    """Test cases for get_cnv_tests_secret_by_name function"""

    @patch("bitwarden.run_command")
    @patch("bitwarden.get_all_cnv_tests_secrets")
    def test_get_cnv_tests_secret_by_name_found(self, mock_get_all, mock_run_command):
        """Test getting secret by name when it exists"""
        with patch.dict(os.environ, {"ACCESS_TOKEN": "test-token"}):
            # Clear cache before test
            get_cnv_tests_secret_by_name.cache_clear()

            # Mock secrets dictionary
            mock_get_all.return_value = {
                "secret1": "uuid-1",
                "secret2": "uuid-2",
            }

            # Mock the run_command response for secret get
            mock_run_command.return_value = (
                True,
                json.dumps({"value": json.dumps({"key": "value2"})}),
                "",
            )

            result = get_cnv_tests_secret_by_name("secret2")

            assert result == {"key": "value2"}
            # Verify run_command was called correctly
            assert mock_run_command.call_count == 1
            call_args = mock_run_command.call_args
            assert call_args.kwargs["command"] == ["bws", "--access-token", "test-token", "secret", "get", "uuid-2"]

    @patch("bitwarden.get_all_cnv_tests_secrets")
    def test_get_cnv_tests_secret_by_name_not_found(self, mock_get_all):
        """Test getting secret by name when it doesn't exist"""
        with patch.dict(os.environ, {"ACCESS_TOKEN": "test-token"}):
            # Clear cache before test
            get_cnv_tests_secret_by_name.cache_clear()

            # Mock secrets dictionary without the requested secret
            mock_get_all.return_value = {
                "existing-secret": "uuid-1",
            }

            with pytest.raises(
                ValueError,
                match="Secret 'nonexistent' not found in Bitwarden",
            ):
                get_cnv_tests_secret_by_name("nonexistent")

    @patch("bitwarden.run_command")
    @patch("bitwarden.get_all_cnv_tests_secrets")
    def test_get_cnv_tests_secret_by_name_invalid_json(self, mock_get_all, mock_run_command):
        """Test getting secret by name when JSON is invalid"""
        with patch.dict(os.environ, {"ACCESS_TOKEN": "test-token"}):
            # Clear cache before test
            get_cnv_tests_secret_by_name.cache_clear()

            # Mock secrets dictionary
            mock_get_all.return_value = {
                "invalid-secret": "uuid-1",
            }

            # Mock the run_command response with invalid JSON
            mock_run_command.return_value = (
                True,
                json.dumps({"value": "invalid json {"}),
                "",
            )

            with pytest.raises(json.JSONDecodeError):
                get_cnv_tests_secret_by_name("invalid-secret")

    @patch("bitwarden.run_command")
    @patch("bitwarden.get_all_cnv_tests_secrets")
    def test_get_cnv_tests_secret_by_name_command_error(self, mock_get_all, mock_run_command):
        """Test bws command error handling for get_cnv_tests_secret_by_name"""
        with patch.dict(os.environ, {"ACCESS_TOKEN": "test-token"}):
            # Clear cache before test
            get_cnv_tests_secret_by_name.cache_clear()

            # Mock secrets dictionary
            mock_get_all.return_value = {
                "secret1": "uuid-1",
            }

            # Mock bws command failure
            mock_run_command.side_effect = subprocess.CalledProcessError(1, "bws", stderr="Secret not accessible")

            with pytest.raises(subprocess.CalledProcessError):
                get_cnv_tests_secret_by_name("secret1")

    @patch("bitwarden.get_all_cnv_tests_secrets")
    def test_get_cnv_tests_secret_by_name_disabled_bitwarden(self, mock_get_all):
        """Test that --disabled-bitwarden flag returns empty dict without calling Bitwarden"""
        from unittest.mock import MagicMock

        # Clear cache before test
        get_cnv_tests_secret_by_name.cache_clear()

        # Create mock session with --disabled-bitwarden set to True
        mock_session = MagicMock()
        mock_session.config.getoption.return_value = True

        result = get_cnv_tests_secret_by_name("any_secret", session=mock_session)

        # Should return empty dict
        assert result == {}
        # Should NOT call get_all_cnv_tests_secrets (early return)
        mock_get_all.assert_not_called()
        # Verify getoption was called with correct argument
        mock_session.config.getoption.assert_called_once_with("--disabled-bitwarden")
