# Generated using Claude cli

"""Unit tests for data_utils module"""

import base64
from unittest.mock import MagicMock, patch

import paramiko
import pytest

from utilities.data_utils import (
    authorized_key,
    base64_encode_str,
    name_prefix,
    private_to_public_key,
)


class TestBase64EncodeStr:
    """Test cases for base64_encode_str function"""

    def test_base64_encode_simple_ascii(self):
        """Test encoding simple ASCII text"""
        text = "hello"
        result = base64_encode_str(text)
        expected = base64.b64encode(text.encode()).decode()
        assert result == expected
        assert result == "aGVsbG8="

    def test_base64_encode_empty_string(self):
        """Test encoding empty string"""
        result = base64_encode_str("")
        assert result == ""
        assert isinstance(result, str)

    def test_base64_encode_special_characters(self):
        """Test encoding special characters"""
        text = "hello@#$%^&*()!~`"
        result = base64_encode_str(text)
        expected = base64.b64encode(text.encode()).decode()
        assert result == expected

    def test_base64_encode_unicode_utf8(self):
        """Test encoding Unicode/UTF-8 text"""
        text = "Hello 世界 🌍"
        result = base64_encode_str(text)
        expected = base64.b64encode(text.encode()).decode()
        assert result == expected

    def test_base64_encode_round_trip(self):
        """Test encoding/decoding round-trip"""
        original = "Test round-trip encoding"
        encoded = base64_encode_str(original)
        decoded = base64.b64decode(encoded.encode()).decode()
        assert decoded == original

    def test_base64_encode_returns_string(self):
        """Test that result is a string type"""
        result = base64_encode_str("test")
        assert isinstance(result, str)

    def test_base64_encode_multiline_text(self):
        """Test encoding multiline text"""
        text = "line1\nline2\nline3"
        result = base64_encode_str(text)
        expected = base64.b64encode(text.encode()).decode()
        assert result == expected

    def test_base64_encode_whitespace(self):
        """Test encoding text with various whitespace"""
        text = "  spaces  \t\ttabs\t\t  \n\nnewlines\n\n  "
        result = base64_encode_str(text)
        expected = base64.b64encode(text.encode()).decode()
        assert result == expected


class TestNamePrefix:
    """Test cases for name_prefix function"""

    def test_name_prefix_single_dot(self):
        """Test extracting prefix with single dot"""
        result = name_prefix("file.txt")
        assert result == "file"

    def test_name_prefix_multiple_dots(self):
        """Test extracting prefix with multiple dots"""
        result = name_prefix("archive.tar.gz")
        assert result == "archive"

    def test_name_prefix_no_dots(self):
        """Test name with no dots returns entire name"""
        result = name_prefix("noextension")
        assert result == "noextension"

    def test_name_prefix_empty_string(self):
        """Test empty string returns empty string"""
        result = name_prefix("")
        assert result == ""

    def test_name_prefix_starts_with_dot(self):
        """Test name starting with dot (hidden file)"""
        result = name_prefix(".hidden")
        assert result == ""

    def test_name_prefix_hidden_file_with_extension(self):
        """Test hidden file with extension"""
        result = name_prefix(".gitignore")
        assert result == ""

    def test_name_prefix_only_dots(self):
        """Test name with only dots"""
        result = name_prefix("...")
        assert result == ""

    def test_name_prefix_complex_filename(self):
        """Test complex filename with multiple components"""
        result = name_prefix("my.project.backup.2024.tar.gz")
        assert result == "my"

    def test_name_prefix_trailing_dot(self):
        """Test name with trailing dot"""
        result = name_prefix("filename.")
        assert result == "filename"


class TestAuthorizedKey:
    """Test cases for authorized_key function"""

    @patch("utilities.data_utils.private_to_public_key")
    def test_authorized_key_correct_format(self, mock_private_to_public):
        """Test authorized_key returns correct SSH format"""
        mock_private_to_public.return_value = "AAAAB3NzaC1yc2EAAAADAQABAAABAQC"

        result = authorized_key("/path/to/id_rsa")

        expected = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC root@exec1.rdocloud"
        assert result == expected
        mock_private_to_public.assert_called_once_with(key="/path/to/id_rsa")

    @patch("utilities.data_utils.private_to_public_key")
    def test_authorized_key_calls_private_to_public_key(self, mock_private_to_public):
        """Test authorized_key calls private_to_public_key with correct path"""
        mock_private_to_public.return_value = "test_base64_key"

        key_path = "/home/user/.ssh/id_rsa"
        authorized_key(key_path)

        mock_private_to_public.assert_called_once_with(key=key_path)

    @patch("utilities.data_utils.private_to_public_key")
    def test_authorized_key_format_components(self, mock_private_to_public):
        """Test authorized_key format has all required components"""
        mock_private_to_public.return_value = "mock_key"

        result = authorized_key("/path/to/key")

        # Verify format: "ssh-rsa <key> root@exec1.rdocloud"
        parts = result.split()
        assert len(parts) == 3
        assert parts[0] == "ssh-rsa"
        assert parts[1] == "mock_key"
        assert parts[2] == "root@exec1.rdocloud"

    @patch("utilities.data_utils.private_to_public_key")
    def test_authorized_key_with_file_not_found(self, mock_private_to_public):
        """Test authorized_key propagates FileNotFoundError"""
        mock_private_to_public.side_effect = FileNotFoundError("Key file not found")

        with pytest.raises(FileNotFoundError):
            authorized_key("/nonexistent/path/id_rsa")

    @patch("utilities.data_utils.private_to_public_key")
    def test_authorized_key_with_ssh_exception(self, mock_private_to_public):
        """Test authorized_key propagates paramiko.SSHException"""
        mock_private_to_public.side_effect = paramiko.SSHException("Invalid key format")

        with pytest.raises(paramiko.SSHException):
            authorized_key("/path/to/invalid_key")


class TestPrivateToPublicKey:
    """Test cases for private_to_public_key function"""

    @patch("utilities.data_utils.paramiko.RSAKey.from_private_key_file")
    def test_private_to_public_key_success(self, mock_from_private_key_file):
        """Test successful private to public key conversion"""
        mock_rsa_key = MagicMock()
        mock_rsa_key.get_base64.return_value = "AAAAB3NzaC1yc2EAAAADAQABAAABAQC"
        mock_from_private_key_file.return_value = mock_rsa_key

        result = private_to_public_key("/path/to/id_rsa")

        assert result == "AAAAB3NzaC1yc2EAAAADAQABAAABAQC"
        mock_from_private_key_file.assert_called_once_with("/path/to/id_rsa")
        mock_rsa_key.get_base64.assert_called_once()

    @patch("utilities.data_utils.paramiko.RSAKey.from_private_key_file")
    def test_private_to_public_key_returns_base64_string(self, mock_from_private_key_file):
        """Test private_to_public_key returns base64 string"""
        mock_rsa_key = MagicMock()
        mock_rsa_key.get_base64.return_value = "base64_encoded_key_data"
        mock_from_private_key_file.return_value = mock_rsa_key

        result = private_to_public_key("/path/to/key")

        assert isinstance(result, str)
        assert result == "base64_encoded_key_data"

    @patch("utilities.data_utils.paramiko.RSAKey.from_private_key_file")
    def test_private_to_public_key_file_not_found(self, mock_from_private_key_file):
        """Test FileNotFoundError when key file doesn't exist"""
        mock_from_private_key_file.side_effect = FileNotFoundError("Private key file not found")

        with pytest.raises(FileNotFoundError):
            private_to_public_key("/nonexistent/key")

        mock_from_private_key_file.assert_called_once_with("/nonexistent/key")

    @patch("utilities.data_utils.paramiko.RSAKey.from_private_key_file")
    def test_private_to_public_key_invalid_key_format(self, mock_from_private_key_file):
        """Test paramiko.SSHException for invalid key format"""
        mock_from_private_key_file.side_effect = paramiko.SSHException("Invalid RSA key format")

        with pytest.raises(paramiko.SSHException):
            private_to_public_key("/path/to/invalid_key")

    @patch("utilities.data_utils.paramiko.RSAKey.from_private_key_file")
    def test_private_to_public_key_password_protected(self, mock_from_private_key_file):
        """Test paramiko.PasswordRequiredException for password-protected key"""
        mock_from_private_key_file.side_effect = paramiko.PasswordRequiredException("Key is password protected")

        with pytest.raises(paramiko.PasswordRequiredException):
            private_to_public_key("/path/to/protected_key")

    @patch("utilities.data_utils.paramiko.RSAKey.from_private_key_file")
    def test_private_to_public_key_with_different_paths(self, mock_from_private_key_file):
        """Test private_to_public_key with various key file paths"""
        mock_rsa_key = MagicMock()
        mock_rsa_key.get_base64.return_value = "test_key"
        mock_from_private_key_file.return_value = mock_rsa_key

        paths = [
            "/home/user/.ssh/id_rsa",
            "/tmp/temp_key",
            "relative/path/key",
            "./local_key",
        ]

        for path in paths:
            result = private_to_public_key(path)
            assert result == "test_key"
