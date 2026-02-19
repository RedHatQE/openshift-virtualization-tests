# Generated using Claude cli

"""Unit tests for artifactory module"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from timeout_sampler import TimeoutExpiredError

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utilities.artifactory import (
    ARTIFACTORY_SECRET_NAME,
    BASE_ARTIFACTORY_LOCATION,
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_header,
    get_artifactory_secret,
    get_http_image_url,
    get_test_artifact_server_url,
)


class TestGetTestArtifactServerUrl:
    """Test cases for get_test_artifact_server_url function"""

    @patch("utilities.artifactory.TimeoutSampler")
    @patch("utilities.artifactory.requests.get")
    @patch("utilities.artifactory.get_artifactory_header")
    @patch(
        "utilities.artifactory.py_config",
        {"servers": {"https_server": "https://test.artifactory.com", "registry_server": "registry.test.com"}},
    )
    def test_get_test_artifact_server_url_https_success(self, mock_get_header, mock_requests_get, mock_sampler):
        """Test successful connection returns correct HTTPS URL"""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = requests.codes.ok
        mock_requests_get.return_value = mock_response

        # Mock header
        mock_get_header.return_value = {"Authorization": "Bearer test-token"}

        # Mock TimeoutSampler to yield the successful response
        mock_sampler.return_value = [mock_response]

        result = get_test_artifact_server_url(schema="https")

        assert result == "https://test.artifactory.com"
        # Note: requests.get is called inside a lambda function within TimeoutSampler,
        # so we verify TimeoutSampler was called with correct parameters instead
        mock_sampler.assert_called_once()
        call_kwargs = mock_sampler.call_args[1]
        assert "func" in call_kwargs
        assert callable(call_kwargs["func"])

    @patch("utilities.artifactory.TimeoutSampler")
    @patch("utilities.artifactory.requests.get")
    @patch("utilities.artifactory.get_artifactory_header")
    @patch(
        "utilities.artifactory.py_config",
        {"servers": {"https_server": "https://test.artifactory.com", "registry_server": "registry.test.com"}},
    )
    def test_get_test_artifact_server_url_registry_schema(self, mock_get_header, mock_requests_get, mock_sampler):
        """Test with registry schema returns correct registry URL"""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = requests.codes.ok
        mock_requests_get.return_value = mock_response

        # Mock header
        mock_get_header.return_value = {"Authorization": "Bearer test-token"}

        # Mock TimeoutSampler to yield the successful response
        mock_sampler.return_value = [mock_response]

        result = get_test_artifact_server_url(schema="registry")

        assert result == "registry.test.com"

    @patch("utilities.artifactory.TimeoutSampler")
    @patch("utilities.artifactory.requests.get")
    @patch("utilities.artifactory.get_artifactory_header")
    @patch("utilities.artifactory.py_config", {"servers": {"https_server": "https://test.artifactory.com"}})
    def test_get_test_artifact_server_url_default_schema(self, mock_get_header, mock_requests_get, mock_sampler):
        """Test default schema is https"""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = requests.codes.ok
        mock_requests_get.return_value = mock_response

        # Mock header
        mock_get_header.return_value = {"Authorization": "Bearer test-token"}

        # Mock TimeoutSampler to yield the successful response
        mock_sampler.return_value = [mock_response]

        result = get_test_artifact_server_url()

        assert result == "https://test.artifactory.com"

    @patch("utilities.artifactory.LOGGER")
    @patch("utilities.artifactory.TimeoutSampler")
    @patch("utilities.artifactory.requests.get")
    @patch("utilities.artifactory.get_artifactory_header")
    @patch("utilities.artifactory.py_config", {"servers": {"https_server": "https://test.artifactory.com"}})
    def test_get_test_artifact_server_url_timeout(self, mock_get_header, mock_requests_get, mock_sampler, mock_logger):
        """Test timeout raises TimeoutExpiredError"""
        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_requests_get.return_value = mock_response

        # Mock header
        mock_get_header.return_value = {"Authorization": "Bearer test-token"}

        # Mock TimeoutSampler to raise timeout
        def timeout_generator():
            yield mock_response
            yield mock_response
            raise TimeoutExpiredError("Timeout")

        mock_sampler.return_value = timeout_generator()

        with pytest.raises(TimeoutExpiredError):
            get_test_artifact_server_url()

        # Verify error logging
        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        assert "Unable to connect to test image server" in error_msg
        assert "500" in error_msg

    @patch("utilities.artifactory.LOGGER")
    @patch("utilities.artifactory.TimeoutSampler")
    @patch("utilities.artifactory.requests.get")
    @patch("utilities.artifactory.get_artifactory_header")
    @patch(
        "utilities.artifactory.py_config",
        {"servers": {"https_server": "https://test.artifactory.com", "registry_server": "registry.test.com"}},
    )
    def test_get_test_artifact_server_url_logging(self, mock_get_header, mock_requests_get, mock_sampler, mock_logger):
        """Test logging behavior"""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = requests.codes.ok
        mock_requests_get.return_value = mock_response

        # Mock header
        mock_get_header.return_value = {"Authorization": "Bearer test-token"}

        # Mock TimeoutSampler
        mock_sampler.return_value = [mock_response]

        get_test_artifact_server_url(schema="https")

        # Verify info logging
        mock_logger.info.assert_called_once()
        info_msg = mock_logger.info.call_args[0][0]
        assert "Testing connectivity to https://test.artifactory.com HTTPS server" in info_msg

    @patch("utilities.artifactory.TimeoutSampler")
    @patch("utilities.artifactory.requests.get")
    @patch("utilities.artifactory.get_artifactory_header")
    @patch("utilities.artifactory.TIMEOUT_1MIN", 60)
    @patch("utilities.artifactory.TIMEOUT_5SEC", 5)
    @patch("utilities.artifactory.py_config", {"servers": {"https_server": "https://test.artifactory.com"}})
    def test_get_test_artifact_server_url_timeout_sampler_params(
        self, mock_get_header, mock_requests_get, mock_sampler
    ):
        """Test TimeoutSampler is called with correct parameters"""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = requests.codes.ok
        mock_requests_get.return_value = mock_response

        # Mock header
        mock_get_header.return_value = {"Authorization": "Bearer test-token"}

        # Mock TimeoutSampler
        mock_sampler.return_value = [mock_response]

        get_test_artifact_server_url()

        # Verify TimeoutSampler was called with correct parameters
        mock_sampler.assert_called_once()
        call_kwargs = mock_sampler.call_args[1]
        assert call_kwargs["wait_timeout"] == 60
        assert call_kwargs["sleep"] == 5
        assert callable(call_kwargs["func"])


class TestGetHttpImageUrl:
    """Test cases for get_http_image_url function"""

    @patch("utilities.artifactory.get_test_artifact_server_url")
    def test_get_http_image_url_returns_correct_format(self, mock_get_server_url):
        """Test returns correct URL format"""
        mock_get_server_url.return_value = "https://test.artifactory.com/"

        result = get_http_image_url("cnv-tests/images", "test-image.qcow2")

        assert result == "https://test.artifactory.com/cnv-tests/images/test-image.qcow2"
        mock_get_server_url.assert_called_once()

    @patch("utilities.artifactory.get_test_artifact_server_url")
    def test_get_http_image_url_calls_get_test_artifact_server_url(self, mock_get_server_url):
        """Test calls get_test_artifact_server_url()"""
        mock_get_server_url.return_value = "https://test.artifactory.com"

        get_http_image_url("test-dir", "test.img")

        mock_get_server_url.assert_called_once_with()

    @patch("utilities.artifactory.get_test_artifact_server_url")
    def test_get_http_image_url_with_empty_directory(self, mock_get_server_url):
        """Test with empty directory path"""
        mock_get_server_url.return_value = "https://test.artifactory.com/"

        result = get_http_image_url("", "test.img")

        assert result == "https://test.artifactory.com//test.img"

    @patch("utilities.artifactory.get_test_artifact_server_url")
    def test_get_http_image_url_timeout_propagation(self, mock_get_server_url):
        """Test TimeoutExpiredError is propagated from get_test_artifact_server_url"""
        mock_get_server_url.side_effect = TimeoutExpiredError("Timeout")

        with pytest.raises(TimeoutExpiredError):
            get_http_image_url("test-dir", "test.img")


class TestGetArtifactoryHeader:
    """Test cases for get_artifactory_header function"""

    def test_get_artifactory_header_returns_correct_format(self):
        """Test returns correct Authorization header format"""
        with patch.dict(os.environ, {"ARTIFACTORY_TOKEN": "test-secret-token"}):
            result = get_artifactory_header()

            assert result == {"Authorization": "Bearer test-secret-token"}

    def test_get_artifactory_header_uses_environment_variable(self):
        """Test uses ARTIFACTORY_TOKEN from environment"""
        with patch.dict(os.environ, {"ARTIFACTORY_TOKEN": "my-token-123"}):
            result = get_artifactory_header()

            assert result["Authorization"] == "Bearer my-token-123"

    def test_get_artifactory_header_raises_key_error_if_not_set(self):
        """Test raises KeyError if ARTIFACTORY_TOKEN not set"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(KeyError):
                get_artifactory_header()

    def test_get_artifactory_header_with_special_characters(self):
        """Test handles tokens with special characters"""
        with patch.dict(os.environ, {"ARTIFACTORY_TOKEN": "token-with-special!@#$%chars"}):
            result = get_artifactory_header()

            assert result["Authorization"] == "Bearer token-with-special!@#$%chars"


class TestGetArtifactorySecret:
    """Test cases for get_artifactory_secret function"""

    @patch("utilities.artifactory.Secret")
    @patch("utilities.artifactory.base64_encode_str")
    def test_get_artifactory_secret_creates_secret_with_correct_parameters(self, mock_base64_encode, mock_secret_class):
        """Test creates Secret with correct parameters"""
        # Mock environment variables
        with patch.dict(os.environ, {"ARTIFACTORY_USER": "test-user", "ARTIFACTORY_TOKEN": "test-token"}):
            # Mock base64 encoding
            mock_base64_encode.side_effect = lambda x: f"base64_{x}"

            # Mock Secret instance
            mock_secret_instance = MagicMock()
            mock_secret_instance.exists = False
            mock_secret_class.return_value = mock_secret_instance

            result = get_artifactory_secret(namespace="test-namespace")

            # Verify Secret was created with correct parameters
            mock_secret_class.assert_called_once_with(
                name=ARTIFACTORY_SECRET_NAME,
                namespace="test-namespace",
                client=None,
                accesskeyid="base64_test-user",
                secretkey="base64_test-token",
            )

            # Verify base64 encoding was called
            assert mock_base64_encode.call_count == 2
            mock_base64_encode.assert_any_call("test-user")
            mock_base64_encode.assert_any_call("test-token")

            assert result == mock_secret_instance

    @patch("utilities.artifactory.Secret")
    @patch("utilities.artifactory.base64_encode_str")
    def test_get_artifactory_secret_deploys_if_not_exists(self, mock_base64_encode, mock_secret_class):
        """Test deploys secret if it doesn't exist"""
        with patch.dict(os.environ, {"ARTIFACTORY_USER": "test-user", "ARTIFACTORY_TOKEN": "test-token"}):
            mock_base64_encode.side_effect = lambda x: f"base64_{x}"

            # Mock Secret instance that doesn't exist
            mock_secret_instance = MagicMock()
            mock_secret_instance.exists = False
            mock_secret_class.return_value = mock_secret_instance

            result = get_artifactory_secret(namespace="test-namespace")

            # Verify deploy was called
            mock_secret_instance.deploy.assert_called_once()
            assert result == mock_secret_instance

    @patch("utilities.artifactory.Secret")
    @patch("utilities.artifactory.base64_encode_str")
    def test_get_artifactory_secret_returns_existing_if_exists(self, mock_base64_encode, mock_secret_class):
        """Test returns existing secret if it exists"""
        with patch.dict(os.environ, {"ARTIFACTORY_USER": "test-user", "ARTIFACTORY_TOKEN": "test-token"}):
            mock_base64_encode.side_effect = lambda x: f"base64_{x}"

            # Mock Secret instance that exists
            mock_secret_instance = MagicMock()
            mock_secret_instance.exists = True
            mock_secret_class.return_value = mock_secret_instance

            result = get_artifactory_secret(namespace="test-namespace")

            # Verify deploy was NOT called
            mock_secret_instance.deploy.assert_not_called()
            assert result == mock_secret_instance

    @patch("utilities.artifactory.Secret")
    def test_get_artifactory_secret_raises_key_error_if_user_not_set(self, mock_secret_class):
        """Test raises KeyError if ARTIFACTORY_USER not set"""
        with patch.dict(os.environ, {"ARTIFACTORY_TOKEN": "test-token"}, clear=True):
            with pytest.raises(KeyError):
                get_artifactory_secret(namespace="test-namespace")

    @patch("utilities.artifactory.Secret")
    def test_get_artifactory_secret_raises_key_error_if_token_not_set(self, mock_secret_class):
        """Test raises KeyError if ARTIFACTORY_TOKEN not set"""
        with patch.dict(os.environ, {"ARTIFACTORY_USER": "test-user"}, clear=True):
            with pytest.raises(KeyError):
                get_artifactory_secret(namespace="test-namespace")

    @patch("utilities.artifactory.Secret")
    @patch("utilities.artifactory.base64_encode_str")
    def test_get_artifactory_secret_uses_correct_secret_name(self, mock_base64_encode, mock_secret_class):
        """Test uses correct secret name constant"""
        with patch.dict(os.environ, {"ARTIFACTORY_USER": "test-user", "ARTIFACTORY_TOKEN": "test-token"}):
            mock_base64_encode.side_effect = lambda x: f"base64_{x}"

            mock_secret_instance = MagicMock()
            mock_secret_instance.exists = False
            mock_secret_class.return_value = mock_secret_instance

            get_artifactory_secret(namespace="test-namespace")

            # Verify the name parameter matches the constant
            call_kwargs = mock_secret_class.call_args[1]
            assert call_kwargs["name"] == ARTIFACTORY_SECRET_NAME
            assert call_kwargs["name"] == "cnv-tests-artifactory-secret"


class TestGetArtifactoryConfigMap:
    """Test cases for get_artifactory_config_map function"""

    @patch("utilities.artifactory.ConfigMap")
    @patch("utilities.artifactory.ssl.get_server_certificate")
    @patch("utilities.artifactory.py_config", {"server_url": "test.artifactory.com"})
    def test_get_artifactory_config_map_creates_with_correct_parameters(self, mock_get_cert, mock_cm_class):
        """Test creates ConfigMap with correct parameters"""
        # Mock certificate
        mock_cert = "-----BEGIN CERTIFICATE-----\nMOCK_CERT\n-----END CERTIFICATE-----"
        mock_get_cert.return_value = mock_cert

        # Mock ConfigMap instance
        mock_cm_instance = MagicMock()
        mock_cm_instance.exists = False
        mock_cm_class.return_value = mock_cm_instance

        result = get_artifactory_config_map(namespace="test-namespace")

        # Verify ConfigMap was created with correct parameters
        mock_cm_class.assert_called_once_with(
            name="artifactory-configmap",
            namespace="test-namespace",
            client=None,
            data={"tlsregistry.crt": mock_cert},
        )

        # Verify SSL certificate was retrieved
        mock_get_cert.assert_called_once_with(addr=("test.artifactory.com", 443))

        assert result == mock_cm_instance

    @patch("utilities.artifactory.ConfigMap")
    @patch("utilities.artifactory.ssl.get_server_certificate")
    @patch("utilities.artifactory.py_config", {"server_url": "test.artifactory.com"})
    def test_get_artifactory_config_map_deploys_if_not_exists(self, mock_get_cert, mock_cm_class):
        """Test deploys ConfigMap if it doesn't exist"""
        mock_cert = "-----BEGIN CERTIFICATE-----\nMOCK_CERT\n-----END CERTIFICATE-----"
        mock_get_cert.return_value = mock_cert

        # Mock ConfigMap instance that doesn't exist
        mock_cm_instance = MagicMock()
        mock_cm_instance.exists = False
        mock_cm_class.return_value = mock_cm_instance

        result = get_artifactory_config_map(namespace="test-namespace")

        # Verify deploy was called
        mock_cm_instance.deploy.assert_called_once()
        assert result == mock_cm_instance

    @patch("utilities.artifactory.ConfigMap")
    @patch("utilities.artifactory.ssl.get_server_certificate")
    @patch("utilities.artifactory.py_config", {"server_url": "test.artifactory.com"})
    def test_get_artifactory_config_map_returns_existing_if_exists(self, mock_get_cert, mock_cm_class):
        """Test returns existing ConfigMap if it exists"""
        mock_cert = "-----BEGIN CERTIFICATE-----\nMOCK_CERT\n-----END CERTIFICATE-----"
        mock_get_cert.return_value = mock_cert

        # Mock ConfigMap instance that exists
        mock_cm_instance = MagicMock()
        mock_cm_instance.exists = True
        mock_cm_class.return_value = mock_cm_instance

        result = get_artifactory_config_map(namespace="test-namespace")

        # Verify deploy was NOT called
        mock_cm_instance.deploy.assert_not_called()
        assert result == mock_cm_instance

    @patch("utilities.artifactory.ConfigMap")
    @patch("utilities.artifactory.ssl.get_server_certificate")
    @patch("utilities.artifactory.py_config", {})
    def test_get_artifactory_config_map_raises_key_error_if_server_url_missing(self, mock_get_cert, mock_cm_class):
        """Test raises KeyError if server_url not in py_config"""
        with pytest.raises(KeyError):
            get_artifactory_config_map(namespace="test-namespace")

    @patch("utilities.artifactory.ConfigMap")
    @patch("utilities.artifactory.ssl.get_server_certificate")
    @patch("utilities.artifactory.py_config", {"server_url": "test.artifactory.com"})
    def test_get_artifactory_config_map_ssl_connection_failure(self, mock_get_cert, mock_cm_class):
        """Test OSError is raised on SSL connection failure"""
        # Mock SSL connection failure
        mock_get_cert.side_effect = OSError("Connection refused")

        with pytest.raises(OSError):
            get_artifactory_config_map(namespace="test-namespace")

        mock_get_cert.assert_called_once_with(addr=("test.artifactory.com", 443))

    @patch("utilities.artifactory.ConfigMap")
    @patch("utilities.artifactory.ssl.get_server_certificate")
    @patch("utilities.artifactory.py_config", {"server_url": "custom.server.com"})
    def test_get_artifactory_config_map_uses_custom_server_url(self, mock_get_cert, mock_cm_class):
        """Test uses server_url from py_config"""
        mock_cert = "-----BEGIN CERTIFICATE-----\nMOCK_CERT\n-----END CERTIFICATE-----"
        mock_get_cert.return_value = mock_cert

        mock_cm_instance = MagicMock()
        mock_cm_instance.exists = False
        mock_cm_class.return_value = mock_cm_instance

        get_artifactory_config_map(namespace="test-namespace")

        # Verify SSL certificate was retrieved from custom server
        mock_get_cert.assert_called_once_with(addr=("custom.server.com", 443))


class TestCleanupArtifactorySecretAndConfigMap:
    """Test cases for cleanup_artifactory_secret_and_config_map function"""

    def test_cleanup_artifactory_secret_and_config_map_cleans_up_secret(self):
        """Test cleans up secret if provided"""
        mock_secret = MagicMock()
        mock_cm = None

        cleanup_artifactory_secret_and_config_map(artifactory_secret=mock_secret, artifactory_config_map=mock_cm)

        mock_secret.clean_up.assert_called_once()

    def test_cleanup_artifactory_secret_and_config_map_cleans_up_config_map(self):
        """Test cleans up config map if provided"""
        mock_secret = None
        mock_cm = MagicMock()

        cleanup_artifactory_secret_and_config_map(artifactory_secret=mock_secret, artifactory_config_map=mock_cm)

        mock_cm.clean_up.assert_called_once()

    def test_cleanup_artifactory_secret_and_config_map_cleans_up_both(self):
        """Test cleans up both if both provided"""
        mock_secret = MagicMock()
        mock_cm = MagicMock()

        cleanup_artifactory_secret_and_config_map(artifactory_secret=mock_secret, artifactory_config_map=mock_cm)

        mock_secret.clean_up.assert_called_once()
        mock_cm.clean_up.assert_called_once()

    def test_cleanup_artifactory_secret_and_config_map_handles_none_secret(self):
        """Test handles None secret value"""
        mock_cm = MagicMock()

        # Should not raise any exception
        cleanup_artifactory_secret_and_config_map(artifactory_secret=None, artifactory_config_map=mock_cm)

        mock_cm.clean_up.assert_called_once()

    def test_cleanup_artifactory_secret_and_config_map_handles_none_config_map(self):
        """Test handles None config map value"""
        mock_secret = MagicMock()

        # Should not raise any exception
        cleanup_artifactory_secret_and_config_map(artifactory_secret=mock_secret, artifactory_config_map=None)

        mock_secret.clean_up.assert_called_once()

    def test_cleanup_artifactory_secret_and_config_map_handles_both_none(self):
        """Test handles both None values"""
        # Should not raise any exception
        cleanup_artifactory_secret_and_config_map(artifactory_secret=None, artifactory_config_map=None)

    def test_cleanup_artifactory_secret_and_config_map_default_parameters(self):
        """Test default parameters are None"""
        # Should not raise any exception with no parameters
        cleanup_artifactory_secret_and_config_map()

    def test_cleanup_artifactory_secret_and_config_map_returns_none(self):
        """Test function returns None"""
        mock_secret = MagicMock()
        mock_cm = MagicMock()

        assert (
            cleanup_artifactory_secret_and_config_map(artifactory_secret=mock_secret, artifactory_config_map=mock_cm)
            is None
        )


class TestArtifactoryConstants:
    """Test cases for artifactory module constants"""

    def test_artifactory_secret_name_constant(self):
        """Test ARTIFACTORY_SECRET_NAME constant is defined"""
        assert ARTIFACTORY_SECRET_NAME == "cnv-tests-artifactory-secret"

    def test_base_artifactory_location_constant(self):
        """Test BASE_ARTIFACTORY_LOCATION constant is defined"""
        assert BASE_ARTIFACTORY_LOCATION == "artifactory/cnv-qe-server-local"
