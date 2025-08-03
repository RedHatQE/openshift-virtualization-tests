"""Unit tests for bitwarden module"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from bitwarden import (
    get_all_cnv_tests_secrets,
    get_bitwarden_secrets_client,
    get_cnv_tests_secret_by_name,
)


class TestGetBitwardenSecretsClient:
    """Test cases for get_bitwarden_secrets_client function"""

    @patch("bitwarden.BitwardenClient")
    def test_get_bitwarden_secrets_client_success(self, mock_client_class):
        """Test successful Bitwarden client creation"""
        with patch.dict(os.environ, {"ACCESS_TOKEN": "test-token", "ORGANIZATION_ID": "test-org"}):
            # Mock the BitwardenClient instance and its methods
            mock_client = MagicMock()
            mock_auth = MagicMock()
            mock_secrets = MagicMock()

            mock_client.auth.return_value = mock_auth
            mock_client.secrets.return_value = mock_secrets
            mock_client_class.return_value = mock_client

            result = get_bitwarden_secrets_client()

            assert result == mock_secrets
            mock_client_class.assert_called_once_with()
            mock_client.auth.assert_called_once_with()
            mock_auth.login_access_token.assert_called_once_with(access_token="test-token")
            mock_client.secrets.assert_called_once_with()

    def test_get_bitwarden_secrets_client_no_token(self):
        """Test when ACCESS_TOKEN or ORGANIZATION_ID is not set"""
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(
                Exception,
                match="Bitwarden client needs ORGANIZATION_ID and ACCESS_TOKEN environment variable set up",
            ),
        ):
            get_bitwarden_secrets_client()


class TestGetAllCnvTestsSecrets:
    """Test cases for get_all_cnv_tests_secrets function"""

    def test_get_all_cnv_tests_secrets(self):
        """Test getting all CNV test secrets"""
        with patch.dict(os.environ, {"ORGANIZATION_ID": "test-org"}):
            mock_client = MagicMock()

            # Mock secret response
            mock_secret1 = MagicMock()
            mock_secret1.key = "test-secret-1"
            mock_secret1.id = "uuid-1"

            mock_secret2 = MagicMock()
            mock_secret2.key = "test-secret-2"
            mock_secret2.id = "uuid-2"

            mock_response = MagicMock()
            mock_response.data.data = [mock_secret1, mock_secret2]
            mock_client.list.return_value = mock_response

            result = get_all_cnv_tests_secrets(mock_client)

            assert len(result) == 2
            assert result == {"test-secret-1": "uuid-1", "test-secret-2": "uuid-2"}
            mock_client.list.assert_called_once_with(organization_id="test-org")


class TestGetCnvTestsSecretByName:
    """Test cases for get_cnv_tests_secret_by_name function"""

    @patch("bitwarden.get_bitwarden_secrets_client")
    @patch("bitwarden.get_all_cnv_tests_secrets")
    def test_get_cnv_tests_secret_by_name_found(self, mock_get_all, mock_get_client):
        """Test getting secret by name when it exists"""
        # Mock client
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock secrets dictionary
        mock_get_all.return_value = {
            "secret1": "uuid-1",
            "secret2": "uuid-2",
        }

        # Mock the secret retrieval
        mock_secret_response = MagicMock()
        mock_secret_response.data.value = json.dumps({"key": "value2"})
        mock_client.get.return_value = mock_secret_response

        result = get_cnv_tests_secret_by_name("secret2")

        assert result == {"key": "value2"}
        mock_client.get.assert_called_once_with(id="uuid-2")

    @patch("bitwarden.get_bitwarden_secrets_client")
    @patch("bitwarden.get_all_cnv_tests_secrets")
    def test_get_cnv_tests_secret_by_name_not_found(self, mock_get_all, mock_get_client):
        """Test getting secret by name when it doesn't exist"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock secrets dictionary without the requested secret
        mock_get_all.return_value = {
            "existing-secret": "uuid-1",
        }

        with pytest.raises(
            AssertionError,
            match="secret nonexistent is either not found or does not have valid values",
        ):
            get_cnv_tests_secret_by_name("nonexistent")
