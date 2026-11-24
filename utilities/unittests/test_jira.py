# Generated using Claude cli

"""Unit tests for jira module"""

import logging
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
import requests

from utilities import jira as jira_module
from utilities.exceptions import JiraServiceAccountError, MissingEnvironmentVariableError
from utilities.jira import get_jira_status, is_jira_open

JIRA_CREDENTIALS_ERROR_MESSAGE = (
    "Please set PYTEST_JIRA_OAUTH_CLIENT_ID, PYTEST_JIRA_OAUTH_CLIENT_SECRET and PYTEST_JIRA_CLOUD_ID, "
    "or PYTEST_JIRA_TOKEN, PYTEST_JIRA_URL and PYTEST_JIRA_USERNAME environment variables"
)
SERVICE_ACCOUNT_ENV = {
    "PYTEST_JIRA_OAUTH_CLIENT_ID": "service-account-client-id",
    "PYTEST_JIRA_OAUTH_CLIENT_SECRET": "service-account-client-secret",
    "PYTEST_JIRA_CLOUD_ID": "service-account-cloud-id",
}
SERVICE_ACCOUNT_GATEWAY_URL = "https://api.atlassian.com/ex/jira/service-account-cloud-id"
USER_TOKEN_CLIENT_KWARGS = {
    "timeout": 15,
}


class FakeJiraError(Exception):
    """Stand-in for jira.JIRAError, whose package utilities/unittests/conftest.py mocks."""

    def __init__(self, status_code: int | None = None) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


@pytest.fixture(autouse=True)
def isolated_jira_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test an empty client cache and no ambient Jira env."""
    monkeypatch.setattr(jira_module, "_SERVICE_ACCOUNT_CLIENTS", {})
    for name in (
        *jira_module.SERVICE_ACCOUNT_VARIABLES,
        "PYTEST_JIRA_URL",
        "PYTEST_JIRA_TOKEN",
        "PYTEST_JIRA_USERNAME",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def service_account_token_endpoint() -> Iterator[MagicMock]:
    """Mock the Atlassian token endpoint with a successful one-hour response."""
    with patch("utilities.jira.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.json.return_value = {
            "access_token": "service-account-token",
            "expires_in": 3600,
        }
        yield mock_post


@pytest.fixture
def service_account_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Export a complete Jira Cloud service-account credential set."""
    for name, value in SERVICE_ACCOUNT_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def user_token_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Export the retiring user + API token credential pair."""
    monkeypatch.setenv("PYTEST_JIRA_URL", "https://jira.example.com")
    monkeypatch.setenv("PYTEST_JIRA_TOKEN", "user-token")
    monkeypatch.setenv("PYTEST_JIRA_USERNAME", "test@example.com")


class TestGetJiraStatus:
    """Test cases for get_jira_status function"""

    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.os.getenv")
    def test_get_jira_status_with_valid_credentials(self, mock_getenv, mock_jira_class):
        """Test get_jira_status with valid JIRA credentials returns status"""
        # Setup
        mock_getenv.side_effect = lambda key, default=None: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
            "PYTEST_JIRA_USERNAME": "test@example.com",
        }.get(key, default)

        mock_issue = MagicMock()
        mock_issue.fields.status.name = "In Progress"
        mock_jira_instance = MagicMock()
        mock_jira_instance.issue.return_value = mock_issue
        mock_jira_class.return_value = mock_jira_instance

        # Execute
        result = get_jira_status("CNV-12345")

        # Verify
        assert result == "in progress", f"Unexpected status: {result}"
        mock_jira_class.assert_called_once_with(
            server="https://jira.example.com",
            basic_auth=("test@example.com", "test-token"),
            **USER_TOKEN_CLIENT_KWARGS,
        )
        mock_jira_instance.issue.assert_called_once_with(id="CNV-12345")

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.LOGGER")
    @patch("utilities.jira.os.getenv")
    def test_get_jira_status_conformance_mode_no_credentials_returns_open(
        self, mock_getenv, mock_logger, mock_py_config
    ):
        """Test get_jira_status in conformance mode without credentials returns 'open'"""
        # Setup
        mock_getenv.return_value = None
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
    @patch("utilities.jira.os.getenv")
    def test_get_jira_status_no_credentials_non_conformance_raises_error(self, mock_getenv, mock_py_config):
        """Test get_jira_status without credentials in non-conformance mode raises MissingEnvironmentVariableError"""
        # Setup
        mock_getenv.return_value = None
        mock_py_config.get.return_value = False  # conformance_tests = False

        # Execute & Verify
        with pytest.raises(MissingEnvironmentVariableError) as exc_info:
            get_jira_status("CNV-12345")

        assert str(exc_info.value) == JIRA_CREDENTIALS_ERROR_MESSAGE, (
            f"Unexpected error for missing credentials: {exc_info.value}"
        )

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.os.getenv")
    def test_get_jira_status_only_token_set_raises_error(self, mock_getenv, mock_py_config):
        """Test get_jira_status with only token set raises MissingEnvironmentVariableError"""
        # Setup
        mock_getenv.side_effect = lambda key, default=None: {
            "PYTEST_JIRA_TOKEN": "test-token",
        }.get(key, default)
        mock_py_config.get.return_value = False  # conformance_tests = False

        # Execute & Verify
        with pytest.raises(MissingEnvironmentVariableError) as exc_info:
            get_jira_status("CNV-12345")

        assert str(exc_info.value) == JIRA_CREDENTIALS_ERROR_MESSAGE, (
            f"Unexpected error for missing credentials: {exc_info.value}"
        )

    @patch("utilities.jira.py_config")
    @patch("utilities.jira.os.getenv")
    def test_get_jira_status_only_url_set_raises_error(self, mock_getenv, mock_py_config):
        """Test get_jira_status with only URL set raises MissingEnvironmentVariableError"""
        # Setup
        mock_getenv.side_effect = lambda key, default=None: {
            "PYTEST_JIRA_URL": "https://jira.example.com",
        }.get(key, default)
        mock_py_config.get.return_value = False  # conformance_tests = False

        # Execute & Verify
        with pytest.raises(MissingEnvironmentVariableError) as exc_info:
            get_jira_status("CNV-12345")

        assert str(exc_info.value) == JIRA_CREDENTIALS_ERROR_MESSAGE, (
            f"Unexpected error for missing credentials: {exc_info.value}"
        )

    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.LOGGER")
    @patch("utilities.jira.os.getenv")
    def test_get_jira_status_logs_returned_status(self, mock_getenv, mock_logger, mock_jira_class):
        """Test get_jira_status logs the returned status"""
        # Setup
        mock_getenv.side_effect = lambda key, default=None: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
            "PYTEST_JIRA_USERNAME": "test@example.com",
        }.get(key, default)

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

    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.os.getenv")
    def test_get_jira_status_with_closed_status(self, mock_getenv, mock_jira_class):
        """Test get_jira_status returns 'closed' status correctly"""
        # Setup
        mock_getenv.side_effect = lambda key, default=None: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
            "PYTEST_JIRA_USERNAME": "test@example.com",
        }.get(key, default)

        mock_issue = MagicMock()
        mock_issue.fields.status.name = "Closed"
        mock_jira_instance = MagicMock()
        mock_jira_instance.issue.return_value = mock_issue
        mock_jira_class.return_value = mock_jira_instance

        # Execute
        result = get_jira_status("CNV-99999")

        # Verify
        assert result == "closed"

    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.os.getenv")
    def test_get_jira_status_with_on_qa_status(self, mock_getenv, mock_jira_class):
        """Test get_jira_status returns 'on_qa' status correctly"""
        # Setup
        mock_getenv.side_effect = lambda key, default=None: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
            "PYTEST_JIRA_USERNAME": "test@example.com",
        }.get(key, default)

        mock_issue = MagicMock()
        mock_issue.fields.status.name = "ON_QA"
        mock_jira_instance = MagicMock()
        mock_jira_instance.issue.return_value = mock_issue
        mock_jira_class.return_value = mock_jira_instance

        # Execute
        result = get_jira_status("CNV-88888")

        # Verify
        assert result == "on_qa"

    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.os.getenv")
    def test_get_jira_status_with_verified_status(self, mock_getenv, mock_jira_class):
        """Test get_jira_status returns 'verified' status correctly"""
        # Setup
        mock_getenv.side_effect = lambda key, default=None: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
            "PYTEST_JIRA_USERNAME": "test@example.com",
        }.get(key, default)

        mock_issue = MagicMock()
        mock_issue.fields.status.name = "Verified"
        mock_jira_instance = MagicMock()
        mock_jira_instance.issue.return_value = mock_issue
        mock_jira_class.return_value = mock_jira_instance

        # Execute
        result = get_jira_status("CNV-77777")

        # Verify
        assert result == "verified"

    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.os.getenv")
    def test_get_jira_status_with_release_pending_status(self, mock_getenv, mock_jira_class):
        """Test get_jira_status returns 'release pending' status correctly"""
        # Setup
        mock_getenv.side_effect = lambda key, default=None: {
            "PYTEST_JIRA_TOKEN": "test-token",
            "PYTEST_JIRA_URL": "https://jira.example.com",
            "PYTEST_JIRA_USERNAME": "test@example.com",
        }.get(key, default)

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


class TestGetJiraStatusServiceAccount:
    """Test cases for get_jira_status with a Jira Cloud service account"""

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_uses_service_account_gateway(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test get_jira_status mints an access token and talks to the cloud gateway"""
        # Setup
        mock_issue = MagicMock()
        mock_issue.fields.status.name = "In Progress"
        mock_jira_class.return_value.issue.return_value = mock_issue

        # Execute
        result = get_jira_status("CNV-12345")

        # Verify
        assert result == "in progress", f"Unexpected status: {result}"
        service_account_token_endpoint.assert_called_once_with(
            url="https://auth.atlassian.com/oauth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": "service-account-client-id",
                "client_secret": "service-account-client-secret",
            },
            timeout=15,
            allow_redirects=False,
        )
        mock_jira_class.assert_called_once_with(
            server=SERVICE_ACCOUNT_GATEWAY_URL,
            token_auth="service-account-token",
            timeout=15,
            get_server_info=False,
            logging=False,
        )
        mock_jira_class.return_value.issue.assert_called_once_with(id="CNV-12345")

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_prefers_service_account_over_user_token(
        self, mock_jira_class, service_account_environment, user_token_environment, service_account_token_endpoint
    ):
        """Test get_jira_status uses the service account when both credentials are set"""
        # Execute
        get_jira_status("CNV-12345")

        # Verify
        assert mock_jira_class.call_args.kwargs["token_auth"] == "service-account-token", (
            f"Expected the service account client, got {mock_jira_class.call_args}"
        )
        assert "basic_auth" not in mock_jira_class.call_args.kwargs, "The user pair was used"

    def test_get_jira_status_rejected_service_account_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test get_jira_status reports a rejected credential with Atlassian's own reason"""
        # Setup
        service_account_token_endpoint.return_value = MagicMock(status_code=401)
        service_account_token_endpoint.return_value.json.return_value = {"error": "invalid_client"}

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        message = str(exc_info.value)
        assert "HTTP 401" in message, f"HTTP status missing from the error: {message}"
        assert "invalid_client" in message, f"Atlassian's reason missing from the error: {message}"
        assert SERVICE_ACCOUNT_ENV["PYTEST_JIRA_OAUTH_CLIENT_SECRET"] not in message, (
            f"The client secret leaked into the error: {message}"
        )

    def test_get_jira_status_rejected_credential_without_json_body_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a rejected credential whose body is not JSON still reports the HTTP status"""
        # Setup
        service_account_token_endpoint.return_value = MagicMock(status_code=400)
        service_account_token_endpoint.return_value.json.side_effect = ValueError("not json")

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "HTTP 400" in str(exc_info.value), f"HTTP status missing: {exc_info.value}"

    def test_get_jira_status_service_account_without_access_token_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test get_jira_status raises when the token response carries no access token"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {"expires_in": 3600}

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "no usable access token" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    def test_get_jira_status_service_account_without_expiry_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test get_jira_status raises rather than guess a token lifetime"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {"access_token": "service-account-token"}

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "no expiry" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    def test_get_jira_status_service_account_with_non_numeric_expiry_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test get_jira_status raises when the token expiry is not a number"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {
            "access_token": "service-account-token",
            "expires_in": "soon",
        }

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "unusable expires_in" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    def test_get_jira_status_rejects_a_token_body_that_is_not_an_object(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a JSON token body that is not an object raises the documented error"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = ["not", "an", "object"]

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "not a JSON object" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    def test_get_jira_status_mint_transport_error_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test get_jira_status wraps a transport failure while minting"""
        # Setup
        service_account_token_endpoint.side_effect = requests.ConnectionError("token endpoint unreachable")

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "ConnectionError" in str(exc_info.value), f"Transport class missing: {exc_info.value}"

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_reuses_the_cached_client(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test get_jira_status mints once and reuses the client for repeated reads"""
        # Execute
        get_jira_status("CNV-12345")
        get_jira_status("CNV-54321")

        # Verify
        assert service_account_token_endpoint.call_count == 1, (
            f"Expected one mint, got {service_account_token_endpoint.call_count}"
        )
        assert mock_jira_class.call_count == 1, f"Expected one client, got {mock_jira_class.call_count}"

    @patch("utilities.jira.monotonic")
    @patch("utilities.jira.JIRA")
    def test_get_jira_status_reuses_a_token_outside_the_refresh_margin(
        self, mock_jira_class, mock_monotonic, service_account_environment, service_account_token_endpoint
    ):
        """Test a token that is not yet inside the refresh margin is reused"""
        # Setup
        mock_monotonic.return_value = 1000.0

        # Execute
        get_jira_status("CNV-12345")
        mock_monotonic.return_value = 1000.0 + 3600 - 180
        get_jira_status("CNV-12345")

        # Verify
        assert service_account_token_endpoint.call_count == 1, (
            f"Expected no second mint outside the margin, got {service_account_token_endpoint.call_count}"
        )

    @patch("utilities.jira.monotonic")
    @patch("utilities.jira.JIRA")
    def test_get_jira_status_remints_inside_the_refresh_margin(
        self, mock_jira_class, mock_monotonic, service_account_environment, service_account_token_endpoint
    ):
        """Test a token inside the refresh margin is replaced before it expires"""
        # Setup
        mock_monotonic.return_value = 1000.0

        # Execute
        get_jira_status("CNV-12345")
        mock_monotonic.return_value = 1000.0 + 3600 - 60
        get_jira_status("CNV-12345")

        # Verify
        assert service_account_token_endpoint.call_count == 2, (
            f"Expected a second mint inside the margin, got {service_account_token_endpoint.call_count}"
        )

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_retries_once_when_the_cached_token_is_revoked(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test a revoked cached token is retired, closed and the read retried once"""
        # Setup
        mock_issue = MagicMock()
        mock_issue.fields.status.name = "New"
        stale_client = MagicMock()
        stale_client.issue.side_effect = [mock_issue, FakeJiraError(status_code=401)]
        fresh_client = MagicMock()
        fresh_client.issue.return_value = mock_issue
        mock_jira_class.side_effect = [stale_client, fresh_client]
        service_account_token_endpoint.return_value.json.side_effect = [
            {"access_token": "rejected-token", "expires_in": 3600},
            {"access_token": "replacement-token", "expires_in": 3600},
        ]
        get_jira_status("CNV-12345")

        # Execute
        with patch("utilities.jira.JIRAError", FakeJiraError):
            result = get_jira_status("CNV-54321")

        # Verify
        assert result == "new", f"Unexpected status after the retry: {result}"
        assert service_account_token_endpoint.call_count == 2, (
            f"Expected a second mint after the 401, got {service_account_token_endpoint.call_count}"
        )
        assert mock_jira_class.call_count == 2, f"Expected a fresh client, got {mock_jira_class.call_count}"
        stale_client.close.assert_called_once()
        fresh_client.close.assert_not_called()
        assert mock_jira_class.call_args.kwargs["token_auth"] == "replacement-token", (
            f"The retry reused the rejected token: {mock_jira_class.call_args}"
        )

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_does_not_retry_a_freshly_minted_token(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test a 401 on a token minted for this call fails fast instead of minting again"""
        # Setup
        mock_jira_class.return_value.issue.side_effect = FakeJiraError(status_code=401)

        # Execute & Verify
        with patch("utilities.jira.JIRAError", FakeJiraError), pytest.raises(JiraServiceAccountError):
            get_jira_status("CNV-12345")

        assert service_account_token_endpoint.call_count == 1, (
            f"A fresh token must not be re-minted, got {service_account_token_endpoint.call_count}"
        )

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_read_failure_reports_issue_key_and_status(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test an unreadable issue is reported with its key and HTTP status"""
        # Setup
        mock_jira_class.return_value.issue.side_effect = FakeJiraError(status_code=404)

        # Execute & Verify
        with patch("utilities.jira.JIRAError", FakeJiraError), pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        message = str(exc_info.value)
        assert "CNV-12345" in message, f"Issue key missing: {message}"
        assert "HTTP 404" in message, f"HTTP status missing: {message}"

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_read_failure_keeps_the_cached_client(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test a non-401 read failure does not throw away a usable client"""
        # Setup
        mock_jira_class.return_value.issue.side_effect = FakeJiraError(status_code=500)

        # Execute
        with patch("utilities.jira.JIRAError", FakeJiraError), pytest.raises(JiraServiceAccountError):
            get_jira_status("CNV-12345")

        # Verify
        assert len(jira_module._SERVICE_ACCOUNT_CLIENTS) == 1, "A 500 dropped the cached client"
        mock_jira_class.return_value.close.assert_not_called()

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_read_failure_has_no_chained_context(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test the read failure carries no chained exception that could print the gateway url"""
        # Setup
        mock_jira_class.return_value.issue.side_effect = FakeJiraError(status_code=500)

        # Execute & Verify
        with patch("utilities.jira.JIRAError", FakeJiraError), pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert exc_info.value.__cause__ is None, "A chained cause would print the gateway url"
        assert exc_info.value.__context__ is None, "A chained context would print the gateway url"

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_transport_failure_hides_the_cloud_id(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test a network failure is reported without the gateway url holding the cloud id"""
        # Setup
        cloud_id = SERVICE_ACCOUNT_ENV["PYTEST_JIRA_CLOUD_ID"]
        mock_jira_class.return_value.issue.side_effect = requests.ConnectionError(
            f"Max retries exceeded with url: /ex/jira/{cloud_id}/rest/api/2/issue/CNV-12345"
        )

        # Execute & Verify
        with patch("utilities.jira.JIRAError", FakeJiraError), pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "ConnectionError" in str(exc_info.value), f"Transport class missing: {exc_info.value}"
        assert cloud_id not in str(exc_info.value), f"The cloud id leaked into the error: {exc_info.value}"
        assert exc_info.value.__context__ is None, "A chained context would print the gateway url"

    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.LOGGER")
    def test_get_jira_status_failure_logs_no_cloud_id_and_no_credentials(
        self, mock_logger, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test no log line carries the cloud id, the client secret or the minted token"""
        # Setup
        mock_jira_class.return_value.issue.side_effect = FakeJiraError(status_code=503)

        # Execute
        with patch("utilities.jira.JIRAError", FakeJiraError), pytest.raises(JiraServiceAccountError):
            get_jira_status("CNV-12345")

        # Verify
        rendered_calls = str(mock_logger.mock_calls)
        for sensitive in (
            SERVICE_ACCOUNT_ENV["PYTEST_JIRA_CLOUD_ID"],
            SERVICE_ACCOUNT_ENV["PYTEST_JIRA_OAUTH_CLIENT_SECRET"],
            "service-account-token",
        ):
            assert sensitive not in rendered_calls, f"{sensitive} leaked into a log line: {rendered_calls}"

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_falls_back_to_user_token(self, mock_jira_class, user_token_environment):
        """Test the user + API token pair is used when no service account is configured"""
        # Execute
        get_jira_status("CNV-12345")
        get_jira_status("CNV-54321")

        # Verify
        assert mock_jira_class.call_args.kwargs == {
            "server": "https://jira.example.com",
            "basic_auth": ("test@example.com", "user-token"),
            **USER_TOKEN_CLIENT_KWARGS,
        }, f"Unexpected client arguments: {mock_jira_class.call_args}"

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_partial_service_account_falls_back(
        self, mock_jira_class, user_token_environment, monkeypatch
    ):
        """Test a half-configured service account falls back to the user + token pair"""
        # Setup
        monkeypatch.setenv("PYTEST_JIRA_OAUTH_CLIENT_ID", "service-account-client-id")
        monkeypatch.setenv("PYTEST_JIRA_OAUTH_CLIENT_SECRET", "service-account-client-secret")

        # Execute
        get_jira_status("CNV-12345")

        # Verify
        assert "basic_auth" in mock_jira_class.call_args.kwargs, (
            f"The user pair was not used: {mock_jira_class.call_args}"
        )

    @patch("utilities.jira.py_config")
    def test_get_jira_status_conformance_run_assumes_open(self, mock_py_config):
        """Test a credential-less conformance run assumes the issue is open"""
        # Setup
        mock_py_config.get.return_value = True

        # Execute
        result = get_jira_status("CNV-12345")

        # Verify
        assert result == "open", f"Unexpected status: {result}"

    def test_get_jira_status_rejects_a_non_json_token_response(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a successful token response whose body is not JSON raises the documented error"""
        # Setup
        service_account_token_endpoint.return_value.json.side_effect = ValueError("not json")

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "not JSON" in str(exc_info.value), f"Unexpected error: {exc_info.value}"
        assert exc_info.value.__context__ is None, "A chained context can carry the token body"

    def test_get_jira_status_rejected_credential_with_array_body_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a rejected credential whose body is a JSON array still reports the HTTP status"""
        # Setup
        service_account_token_endpoint.return_value = MagicMock(status_code=403)
        service_account_token_endpoint.return_value.json.return_value = ["forbidden"]

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "HTTP 403" in str(exc_info.value), f"HTTP status missing: {exc_info.value}"

    def test_get_jira_status_rejected_credential_does_not_echo_the_secret(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a reflected token request cannot leak the client secret through the error"""
        # Setup
        secret = SERVICE_ACCOUNT_ENV["PYTEST_JIRA_OAUTH_CLIENT_SECRET"]
        service_account_token_endpoint.return_value = MagicMock(status_code=400)
        service_account_token_endpoint.return_value.json.return_value = {
            "error": "invalid_request",
            "error_description": f"request body: client_secret={secret}",
        }

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        message = str(exc_info.value)
        assert "invalid_request" in message, f"The OAuth error code is missing: {message}"
        assert secret not in message, f"The client secret leaked into the error: {message}"

    def test_get_jira_status_service_account_with_zero_expiry_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a zero token lifetime is rejected instead of reminting on every call"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {
            "access_token": "service-account-token",
            "expires_in": 0,
        }

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "non-finite or non-positive expires_in" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    def test_get_jira_status_service_account_with_nan_expiry_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a NaN token lifetime is rejected: it would compare False against every deadline"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {
            "access_token": "service-account-token",
            "expires_in": float("nan"),
        }

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "non-finite or non-positive expires_in" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_empty_issue_body_raises(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test an empty issue resource is reported as an empty response"""
        # Setup
        mock_jira_class.return_value.issue.side_effect = NotImplementedError("cannot instantiate empty resources")

        # Execute & Verify
        with patch("utilities.jira.JIRAError", FakeJiraError), pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "empty response" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    @patch("utilities.jira.JIRA")
    @patch("utilities.jira.LOGGER")
    def test_get_jira_status_retry_is_logged_without_sensitive_data(
        self, mock_logger, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test a reused token rejection is logged with the issue key only"""
        # Setup
        mock_issue = MagicMock()
        mock_issue.fields.status.name = "New"
        mock_jira_class.return_value.issue.side_effect = [
            mock_issue,
            FakeJiraError(status_code=401),
            mock_issue,
        ]
        get_jira_status("CNV-12345")

        # Execute
        with patch("utilities.jira.JIRAError", FakeJiraError):
            get_jira_status("CNV-54321")

        # Verify
        warning = str(mock_logger.warning.call_args)
        assert "CNV-54321" in warning, f"Issue key missing from the warning: {warning}"
        assert "401" in warning, f"HTTP status missing from the warning: {warning}"
        for sensitive in (
            SERVICE_ACCOUNT_ENV["PYTEST_JIRA_CLOUD_ID"],
            SERVICE_ACCOUNT_ENV["PYTEST_JIRA_OAUTH_CLIENT_SECRET"],
            "service-account-token",
        ):
            assert sensitive not in warning, f"{sensitive} leaked into the warning: {warning}"

    @patch("utilities.jira.monotonic")
    @patch("utilities.jira.JIRA")
    def test_get_jira_status_closes_the_client_it_replaces(
        self, mock_jira_class, mock_monotonic, service_account_environment, service_account_token_endpoint
    ):
        """Test a client replaced at remint time is closed before the new one is cached"""
        # Setup
        first_client = MagicMock()
        second_client = MagicMock()
        mock_jira_class.side_effect = [first_client, second_client]
        mock_monotonic.return_value = 1000.0

        # Execute
        get_jira_status("CNV-12345")
        mock_monotonic.return_value = 1000.0 + 3600 - 60
        get_jira_status("CNV-54321")

        # Verify
        first_client.close.assert_called_once()
        second_client.close.assert_not_called()
        cached_client, _ = jira_module._SERVICE_ACCOUNT_CLIENTS[
            ("service-account-client-id", "service-account-cloud-id")
        ]
        assert cached_client is second_client, "The replacement client is not the cached one"

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_forgets_a_client_whose_fresh_token_is_rejected(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test a rejected fresh token is retired so later calls pay a single mint"""
        # Setup
        mock_jira_class.return_value.issue.side_effect = FakeJiraError(status_code=401)

        # Execute
        with patch("utilities.jira.JIRAError", FakeJiraError), pytest.raises(JiraServiceAccountError):
            get_jira_status("CNV-12345")

        # Verify
        assert not jira_module._SERVICE_ACCOUNT_CLIENTS, "A rejected client stayed cached"
        mock_jira_class.return_value.close.assert_called_once()

    @patch("utilities.jira.requests.post")
    def test_get_jira_status_mint_transport_error_keeps_no_cause(self, mock_post, service_account_environment):
        """Test a mint transport failure does not chain the request that carries the secret"""
        # Setup
        mock_post.side_effect = requests.ConnectionError("token endpoint unreachable")

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert exc_info.value.__cause__ is None, "A chained cause exposes the request body"
        assert exc_info.value.__context__ is None, "A chained context exposes the request body"

    def test_get_jira_status_service_account_with_infinite_expiry_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test an infinite token lifetime is rejected rather than cached forever"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {
            "access_token": "service-account-token",
            "expires_in": float("inf"),
        }

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "non-finite or non-positive expires_in" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    def test_get_jira_status_service_account_with_expiry_inside_the_margin_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a token that is already inside the refresh margin is rejected"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {
            "access_token": "service-account-token",
            "expires_in": 60,
        }

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "refresh margin" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    def test_get_jira_status_unusable_expiry_does_not_echo_the_secret(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a reflected request body in expires_in cannot leak the client secret"""
        # Setup
        secret = SERVICE_ACCOUNT_ENV["PYTEST_JIRA_OAUTH_CLIENT_SECRET"]
        service_account_token_endpoint.return_value.json.return_value = {
            "access_token": "service-account-token",
            "expires_in": f"client_secret={secret}",
        }

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        message = str(exc_info.value)
        assert "unusable expires_in (str)" in message, f"The value type is not reported: {message}"
        assert secret not in message, f"The client secret leaked into the error: {message}"
        assert exc_info.value.__context__ is None, "A chained context can carry the reflected value"

    @patch("utilities.jira.py_config")
    def test_get_jira_status_partial_service_account_without_user_token_names_the_missing_variable(
        self, mock_py_config, monkeypatch
    ):
        """Test a partial credential set without a fallback names the missing variable"""
        # Setup
        mock_py_config.get.return_value = False
        monkeypatch.setenv("PYTEST_JIRA_OAUTH_CLIENT_ID", "service-account-client-id")
        monkeypatch.setenv("PYTEST_JIRA_OAUTH_CLIENT_SECRET", "service-account-client-secret")

        # Execute & Verify
        with pytest.raises(MissingEnvironmentVariableError) as exc_info:
            get_jira_status("CNV-12345")

        message = str(exc_info.value)
        assert "not set: PYTEST_JIRA_CLOUD_ID" in message, f"Missing variable not named: {message}"
        assert "PYTEST_JIRA_OAUTH_CLIENT_ID" not in message.split("not set:")[1], (
            f"An exported variable is listed as missing: {message}"
        )

    def test_get_jira_status_service_account_with_expiry_just_above_the_margin_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a token whose reuse window is shorter than a margin is refused"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {
            "access_token": "service-account-token",
            "expires_in": 121,
        }

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "less than twice" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    def test_get_jira_status_service_account_with_overflowing_expiry_raises(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test an expiry too large for a float raises the documented error"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {
            "access_token": "service-account-token",
            "expires_in": int("1" * 400),
        }

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "unusable expires_in (int)" in str(exc_info.value), f"Unexpected error: {exc_info.value}"
        assert exc_info.value.__context__ is None, "A chained context can carry the value"

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_accepts_a_token_at_the_reuse_boundary(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test a lifetime of exactly twice the refresh margin is accepted and reused"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {
            "access_token": "service-account-token",
            "expires_in": 2 * jira_module.TOKEN_REFRESH_MARGIN_SECONDS,
        }

        # Execute
        get_jira_status("CNV-12345")
        get_jira_status("CNV-54321")

        # Verify
        assert service_account_token_endpoint.call_count == 1, (
            f"Expected the boundary token to be reused, got {service_account_token_endpoint.call_count} mints"
        )

    def test_get_jira_status_rejects_a_non_string_access_token(
        self, service_account_environment, service_account_token_endpoint
    ):
        """Test a JSON array token is refused instead of formatted into a header"""
        # Setup
        service_account_token_endpoint.return_value.json.return_value = {
            "access_token": ["unexpected"],
            "expires_in": 3600,
        }

        # Execute & Verify
        with pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "no usable access token" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_issue_without_status_raises(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test a 200 issue body without a status field is reported as such"""
        # Setup
        mock_jira_class.return_value.issue.return_value.fields = MagicMock(spec=[])

        # Execute & Verify
        with patch("utilities.jira.JIRAError", FakeJiraError), pytest.raises(JiraServiceAccountError) as exc_info:
            get_jira_status("CNV-12345")

        assert "response without a status" in str(exc_info.value), f"Unexpected error: {exc_info.value}"

    @patch("utilities.jira.JIRA")
    def test_get_jira_status_cache_hit_restores_the_silenced_logger(
        self, mock_jira_class, service_account_environment, service_account_token_endpoint
    ):
        """Test a cache hit re-silences python-jira's shared logger"""
        # Setup
        get_jira_status("CNV-12345")
        logging.getLogger("jira").setLevel(logging.INFO)

        # Execute
        get_jira_status("CNV-54321")

        # Verify
        assert logging.getLogger("jira").level == logging.CRITICAL, (
            "A cache hit left python-jira's logger at the level another client set"
        )
