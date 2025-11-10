# Generated using Claude cli

"""Unit tests for jira module"""

from unittest.mock import MagicMock, patch

import pytest

from utilities.exceptions import MissingEnvironmentVariableError
from utilities.jira import get_jira_status, is_jira_open


class TestGetJiraStatus:
    """Test cases for get_jira_status function"""

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.os.environ")
    def test_get_jira_status_with_valid_credentials(self, mock_environ, mock_jira_class, mock_py_config):
        """Test get_jira_status with valid JIRA credentials returns status"""
        # Setup
        mock_environ.get.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }.get(key)
        mock_environ.__getitem__.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }[key]

        mock_issue = MagicMock()
        mock_issue.fields.status.name = "In Progress"
        mock_jira_instance = MagicMock()
        mock_jira_instance.issue.return_value = mock_issue
        mock_jira_class.return_value = mock_jira_instance

        # Execute
        result = get_jira_status("CNV-12345")

        # Verify
        assert result == "in progress"
        mock_jira_class.assert_called_once_with(
            token_auth="test-token",
            options={"server": "https://jira.example.com"},
        )
        mock_jira_instance.issue.assert_called_once_with(id="CNV-12345")

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.LOGGER")
    @patch("utilities.jira.os.environ")
    def test_get_jira_status_conformance_mode_no_credentials_returns_open(
        self, mock_environ, mock_logger, mock_py_config
    ):
        """Test get_jira_status in conformance mode without credentials returns 'open'"""
        # Setup
        mock_environ.get.return_value = None
        mock_py_config.get.return_value = True  # conformance_tests = True

        # Execute
        result = get_jira_status("CNV-12345")

        # Verify
        assert result == "open"
        mock_py_config.get.assert_called_once_with("conformance_tests")
        mock_logger.info.assert_called_once_with(
            "Conformance tests without JIRA credentials: assuming CNV-12345 is open"
        )

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.os.environ")
    def test_get_jira_status_no_credentials_non_conformance_raises_error(self, mock_environ, mock_py_config):
        """Test get_jira_status without credentials in non-conformance mode raises MissingEnvironmentVariableError"""
        # Setup
        mock_environ.get.return_value = None
        mock_py_config.get.return_value = False  # conformance_tests = False

        # Execute & Verify
        with pytest.raises(MissingEnvironmentVariableError) as exc_info:
            get_jira_status("CNV-12345")

        assert str(exc_info.value) == "Please set PYTEST_JIRA_TOKEN and PYTEST_JIRA_URL environment variables"

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.os.environ")
    def test_get_jira_status_only_token_set_raises_error(self, mock_environ, mock_py_config):
        """Test get_jira_status with only token set raises MissingEnvironmentVariableError"""
        # Setup
        mock_environ.get.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": None,
        }.get(key)
        mock_py_config.get.return_value = False  # conformance_tests = False

        # Execute & Verify
        with pytest.raises(MissingEnvironmentVariableError) as exc_info:
            get_jira_status("CNV-12345")

        assert str(exc_info.value) == "Please set PYTEST_JIRA_TOKEN and PYTEST_JIRA_URL environment variables"

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.os.environ")
    def test_get_jira_status_only_url_set_raises_error(self, mock_environ, mock_py_config):
        """Test get_jira_status with only URL set raises MissingEnvironmentVariableError"""
        # Setup
        mock_environ.get.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": None,
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }.get(key)
        mock_py_config.get.return_value = False  # conformance_tests = False

        # Execute & Verify
        with pytest.raises(MissingEnvironmentVariableError) as exc_info:
            get_jira_status("CNV-12345")

        assert str(exc_info.value) == "Please set PYTEST_JIRA_TOKEN and PYTEST_JIRA_URL environment variables"

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.LOGGER")
    @patch("utilities.jira.os.environ")
    def test_get_jira_status_logs_returned_status(self, mock_environ, mock_logger, mock_jira_class, mock_py_config):
        """Test get_jira_status logs the returned status"""
        # Setup
        mock_environ.get.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }.get(key)
        mock_environ.__getitem__.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }[key]

        mock_issue = MagicMock()
        mock_issue.fields.status.name = "Open"
        mock_jira_instance = MagicMock()
        mock_jira_instance.issue.return_value = mock_issue
        mock_jira_class.return_value = mock_jira_instance

        # Execute
        result = get_jira_status("CNV-54321")

        # Verify
        assert result == "open"
        mock_logger.info.assert_called_once_with("Jira CNV-54321: status is open")

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.os.environ")
    def test_get_jira_status_with_closed_status(self, mock_environ, mock_jira_class, mock_py_config):
        """Test get_jira_status returns 'closed' status correctly"""
        # Setup
        mock_environ.get.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }.get(key)
        mock_environ.__getitem__.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }[key]

        mock_issue = MagicMock()
        mock_issue.fields.status.name = "Closed"
        mock_jira_instance = MagicMock()
        mock_jira_instance.issue.return_value = mock_issue
        mock_jira_class.return_value = mock_jira_instance

        # Execute
        result = get_jira_status("CNV-99999")

        # Verify
        assert result == "closed"

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.os.environ")
    def test_get_jira_status_with_on_qa_status(self, mock_environ, mock_jira_class, mock_py_config):
        """Test get_jira_status returns 'on_qa' status correctly"""
        # Setup
        mock_environ.get.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }.get(key)
        mock_environ.__getitem__.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }[key]

        mock_issue = MagicMock()
        mock_issue.fields.status.name = "ON_QA"
        mock_jira_instance = MagicMock()
        mock_jira_instance.issue.return_value = mock_issue
        mock_jira_class.return_value = mock_jira_instance

        # Execute
        result = get_jira_status("CNV-88888")

        # Verify
        assert result == "on_qa"

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.os.environ")
    def test_get_jira_status_with_verified_status(self, mock_environ, mock_jira_class, mock_py_config):
        """Test get_jira_status returns 'verified' status correctly"""
        # Setup
        mock_environ.get.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }.get(key)
        mock_environ.__getitem__.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }[key]

        mock_issue = MagicMock()
        mock_issue.fields.status.name = "Verified"
        mock_jira_instance = MagicMock()
        mock_jira_instance.issue.return_value = mock_issue
        mock_jira_class.return_value = mock_jira_instance

        # Execute
        result = get_jira_status("CNV-77777")

        # Verify
        assert result == "verified"

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.os.environ")
    def test_get_jira_status_with_release_pending_status(self, mock_environ, mock_jira_class, mock_py_config):
        """Test get_jira_status returns 'release pending' status correctly"""
        # Setup
        mock_environ.get.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }.get(key)
        mock_environ.__getitem__.side_effect = lambda key: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }[key]

        mock_issue = MagicMock()
        mock_issue.fields.status.name = "Release Pending"
        mock_jira_instance = MagicMock()
        mock_jira_instance.issue.return_value = mock_issue
        mock_jira_class.return_value = mock_jira_instance

        # Execute
        result = get_jira_status("CNV-66666")

        # Verify
        assert result == "release pending"


class TestIsJiraOpen:
    """Test cases for is_jira_open function"""

    @patch("utilities.jira.get_jira_status")
    def test_is_jira_open_with_open_status_returns_true(self, mock_get_status):
        """Test is_jira_open returns True when status is 'open'"""
        # Setup
        mock_get_status.return_value = "open"

        # Execute
        result = is_jira_open("CNV-12345")

        # Verify
        assert result is True
        mock_get_status.assert_called_once_with(jira="CNV-12345")

    @patch("utilities.jira.get_jira_status")
    def test_is_jira_open_with_on_qa_status_returns_false(self, mock_get_status):
        """Test is_jira_open returns False when status is 'on_qa'"""
        # Setup
        mock_get_status.return_value = "on_qa"

        # Execute
        result = is_jira_open("CNV-12345")

        # Verify
        assert result is False

    @patch("utilities.jira.get_jira_status")
    def test_is_jira_open_with_verified_status_returns_false(self, mock_get_status):
        """Test is_jira_open returns False when status is 'verified'"""
        # Setup
        mock_get_status.return_value = "verified"

        # Execute
        result = is_jira_open("CNV-12345")

        # Verify
        assert result is False

    @patch("utilities.jira.get_jira_status")
    def test_is_jira_open_with_release_pending_status_returns_false(self, mock_get_status):
        """Test is_jira_open returns False when status is 'release pending'"""
        # Setup
        mock_get_status.return_value = "release pending"

        # Execute
        result = is_jira_open("CNV-12345")

        # Verify
        assert result is False

    @patch("utilities.jira.get_jira_status")
    def test_is_jira_open_with_closed_status_returns_false(self, mock_get_status):
        """Test is_jira_open returns False when status is 'closed'"""
        # Setup
        mock_get_status.return_value = "closed"

        # Execute
        result = is_jira_open("CNV-12345")

        # Verify
        assert result is False

    @patch("utilities.jira.get_jira_status")
    def test_is_jira_open_with_in_progress_status_returns_true(self, mock_get_status):
        """Test is_jira_open returns True when status is 'in progress'"""
        # Setup
        mock_get_status.return_value = "in progress"

        # Execute
        result = is_jira_open("CNV-12345")

        # Verify
        assert result is True

    @patch("utilities.jira.get_jira_status")
    def test_is_jira_open_with_new_status_returns_true(self, mock_get_status):
        """Test is_jira_open returns True when status is 'new'"""
        # Setup
        mock_get_status.return_value = "new"

        # Execute
        result = is_jira_open("CNV-12345")

        # Verify
        assert result is True

    @patch("utilities.jira.get_jira_status")
    def test_is_jira_open_with_to_do_status_returns_true(self, mock_get_status):
        """Test is_jira_open returns True when status is 'to do'"""
        # Setup
        mock_get_status.return_value = "to do"

        # Execute
        result = is_jira_open("CNV-12345")

        # Verify
        assert result is True

    @patch("utilities.jira.get_jira_status")
    def test_is_jira_open_with_assigned_status_returns_true(self, mock_get_status):
        """Test is_jira_open returns True when status is 'assigned'"""
        # Setup
        mock_get_status.return_value = "assigned"

        # Execute
        result = is_jira_open("CNV-12345")

        # Verify
        assert result is True

    @patch("utilities.jira.get_jira_status")
    def test_is_jira_open_with_post_status_returns_true(self, mock_get_status):
        """Test is_jira_open returns True when status is 'post'"""
        # Setup
        mock_get_status.return_value = "post"

        # Execute
        result = is_jira_open("CNV-12345")

        # Verify
        assert result is True
