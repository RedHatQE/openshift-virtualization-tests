"""Unit tests for construct_datavolume_source_dict in utilities/storage.py"""

import importlib
import sys
from unittest.mock import patch

import pytest

# Other test modules (test_hco, test_ssp) mock utilities.storage in sys.modules.
# Clear the mock and reimport the real module to test actual behavior.
if "utilities.storage" in sys.modules:
    del sys.modules["utilities.storage"]

import utilities.storage

importlib.reload(utilities.storage)
utilities.storage = utilities.storage  # type: ignore[attr-defined]

from utilities.storage import construct_datavolume_source_dict


class TestConstructDatavolumeSourceDictHttp:
    @patch("utilities.storage.validate_file_exists_in_url")
    @patch("utilities.infra.url_excluded_from_validation", return_value=False)
    def test_http_source(self, mock_excluded, mock_validate):
        result = construct_datavolume_source_dict(source="http", url="https://example.com/image.qcow2")
        assert result == {"http": {"url": "https://example.com/image.qcow2"}}
        mock_validate.assert_called_once_with(url="https://example.com/image.qcow2")

    @patch("utilities.storage.validate_file_exists_in_url")
    @patch("utilities.infra.url_excluded_from_validation", return_value=True)
    def test_http_source_excluded_from_validation(self, mock_excluded, mock_validate):
        result = construct_datavolume_source_dict(source="http", url="https://internal.example.com/image.qcow2")
        assert result == {"http": {"url": "https://internal.example.com/image.qcow2"}}
        mock_validate.assert_not_called()

    @patch("utilities.storage.validate_file_exists_in_url")
    @patch("utilities.infra.url_excluded_from_validation", return_value=False)
    def test_http_source_with_secret(self, mock_excluded, mock_validate):
        result = construct_datavolume_source_dict(
            source="http",
            url="https://example.com/image.qcow2",
            secret_name="my-secret",
        )
        assert result == {"http": {"url": "https://example.com/image.qcow2", "secretRef": "my-secret"}}

    @patch("utilities.storage.validate_file_exists_in_url")
    @patch("utilities.infra.url_excluded_from_validation", return_value=False)
    def test_http_source_with_cert_configmap(self, mock_excluded, mock_validate):
        result = construct_datavolume_source_dict(
            source="http",
            url="https://example.com/image.qcow2",
            cert_configmap_name="my-cert-cm",
        )
        assert result == {"http": {"url": "https://example.com/image.qcow2", "certConfigMap": "my-cert-cm"}}

    @patch("utilities.storage.validate_file_exists_in_url")
    @patch("utilities.infra.url_excluded_from_validation", return_value=False)
    def test_http_source_with_secret_and_cert(self, mock_excluded, mock_validate):
        result = construct_datavolume_source_dict(
            source="http",
            url="https://example.com/image.qcow2",
            secret_name="my-secret",
            cert_configmap_name="my-cert-cm",
        )
        assert result == {
            "http": {"url": "https://example.com/image.qcow2", "secretRef": "my-secret", "certConfigMap": "my-cert-cm"}
        }


class TestConstructDatavolumeSourceDictRegistry:
    def test_registry_source(self):
        result = construct_datavolume_source_dict(source="registry", url="docker://registry.example.com/image:latest")
        assert result == {"registry": {"url": "docker://registry.example.com/image:latest"}}

    def test_registry_source_with_secret(self):
        result = construct_datavolume_source_dict(
            source="registry",
            url="docker://registry.example.com/image:latest",
            secret_name="registry-secret",
        )
        assert result == {
            "registry": {"url": "docker://registry.example.com/image:latest", "secretRef": "registry-secret"}
        }

    def test_registry_source_with_cert_configmap(self):
        result = construct_datavolume_source_dict(
            source="registry",
            url="docker://registry.example.com/image:latest",
            cert_configmap_name="registry-cert-cm",
        )
        assert result == {
            "registry": {"url": "docker://registry.example.com/image:latest", "certConfigMap": "registry-cert-cm"}
        }

    def test_registry_source_with_secret_and_cert(self):
        result = construct_datavolume_source_dict(
            source="registry",
            url="docker://registry.example.com/image:latest",
            secret_name="registry-secret",
            cert_configmap_name="registry-cert-cm",
        )
        assert result == {
            "registry": {
                "url": "docker://registry.example.com/image:latest",
                "secretRef": "registry-secret",
                "certConfigMap": "registry-cert-cm",
            }
        }


class TestConstructDatavolumeSourceDictPvc:
    def test_pvc_source_with_namespace(self):
        result = construct_datavolume_source_dict(
            source="pvc",
            source_pvc_name="my-pvc",
            source_pvc_namespace="my-namespace",
        )
        assert result == {"pvc": {"name": "my-pvc", "namespace": "my-namespace"}}

    def test_pvc_source_without_namespace(self):
        result = construct_datavolume_source_dict(source="pvc", source_pvc_name="my-pvc")
        assert result == {"pvc": {"name": "my-pvc"}}
        assert "namespace" not in result["pvc"]


class TestConstructDatavolumeSourceDictBlank:
    def test_blank_source(self):
        result = construct_datavolume_source_dict(source="blank")
        assert result == {"blank": {}}


class TestConstructDatavolumeSourceDictUpload:
    def test_upload_source(self):
        result = construct_datavolume_source_dict(source="upload")
        assert result == {"upload": {}}


class TestConstructDatavolumeSourceDictUnsupported:
    def test_unsupported_source_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported source type: ftp"):
            construct_datavolume_source_dict(source="ftp")
