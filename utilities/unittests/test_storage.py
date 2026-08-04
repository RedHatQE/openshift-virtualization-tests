"""Unit tests for construct_datavolume_source_dict and create_dv in utilities/storage.py"""

import importlib
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

# Other test modules (test_hco, test_ssp) mock utilities.storage in sys.modules.
# Clear the mock and reimport the real module to test actual behavior.
if "utilities.storage" in sys.modules:
    del sys.modules["utilities.storage"]

import utilities.storage

importlib.reload(utilities.storage)

from utilities.storage import construct_datavolume_source_dict, create_dv


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

    @patch.dict("utilities.storage.py_config", {"cpu_arch": "arm64", "cluster_type": "multiarch"})
    def test_registry_source_multiarch_with_cpu_arch(self):
        result = construct_datavolume_source_dict(source="registry", url="docker://registry.example.com/image:latest")
        assert result == {
            "registry": {
                "url": "docker://registry.example.com/image:latest",
                "platform": {"architecture": "arm64"},
            }
        }

    @patch.dict("utilities.storage.py_config", {"cpu_arch": "arm64", "cluster_type": "standard"})
    def test_registry_source_non_multiarch_no_platform(self):
        result = construct_datavolume_source_dict(source="registry", url="docker://registry.example.com/image:latest")
        assert result == {"registry": {"url": "docker://registry.example.com/image:latest"}}
        assert "platform" not in result["registry"]

    @patch.dict("utilities.storage.py_config", {"cluster_type": "multiarch"})
    def test_registry_source_multiarch_no_cpu_arch_no_platform(self):
        result = construct_datavolume_source_dict(source="registry", url="docker://registry.example.com/image:latest")
        assert result == {"registry": {"url": "docker://registry.example.com/image:latest"}}
        assert "platform" not in result["registry"]


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

    def test_pvc_source_with_empty_namespace(self):
        result = construct_datavolume_source_dict(
            source="pvc",
            source_pvc_name="my-pvc",
            source_pvc_namespace="",
        )
        assert result == {"pvc": {"name": "my-pvc", "namespace": ""}}


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


class TestCreateDvArtifactory:
    """Unit tests for create_dv Artifactory credential wiring via ExitStack."""

    @staticmethod
    def _credentials(*, secret_name: str = "artifactory-secret", config_map_name: str = "artifactory-configmap"):
        credentials = MagicMock()
        credentials.secret_name = secret_name
        credentials.cert_configmap_name = config_map_name
        return credentials

    @staticmethod
    @contextmanager
    def _artifactory_cm(credentials):
        yield credentials

    def _mock_data_volume(self, mock_data_volume_class):
        mock_dv = MagicMock()
        mock_data_volume_class.return_value = mock_dv
        mock_data_volume_class.return_value.__enter__ = MagicMock(return_value=mock_dv)
        mock_data_volume_class.return_value.__exit__ = MagicMock(return_value=None)
        return mock_dv

    @patch("utilities.storage.sc_volume_binding_mode_is_wffc", return_value=False)
    @patch("utilities.storage.DataVolume")
    @patch("utilities.storage.validate_file_exists_in_url")
    @patch("utilities.infra.url_excluded_from_validation", return_value=True)
    @patch("utilities.storage.artifactory_credentials")
    def test_create_dv_creates_both_artifactory_resources(
        self,
        mock_artifactory_credentials,
        mock_excluded,
        mock_validate,
        mock_data_volume_class,
        mock_wffc,
    ):
        credentials = self._credentials()
        mock_client = MagicMock()
        mock_artifactory_credentials.side_effect = lambda **kwargs: self._artifactory_cm(credentials)
        mock_dv = self._mock_data_volume(mock_data_volume_class)

        with create_dv(
            dv_name="test-dv",
            namespace="test-ns",
            client=mock_client,
            source="http",
            url="https://example.com/image.qcow2",
            use_artifactory=True,
        ) as dv:
            assert dv is mock_dv

        mock_artifactory_credentials.assert_called_once_with(
            namespace="test-ns",
            client=mock_client,
            create_secret=True,
            create_config_map=True,
        )
        source_dict = mock_data_volume_class.call_args.kwargs["source_dict"]
        assert source_dict["http"]["secretRef"] == "artifactory-secret"
        assert source_dict["http"]["certConfigMap"] == "artifactory-configmap"

    @patch("utilities.storage.sc_volume_binding_mode_is_wffc", return_value=False)
    @patch("utilities.storage.DataVolume")
    @patch("utilities.storage.validate_file_exists_in_url")
    @patch("utilities.infra.url_excluded_from_validation", return_value=True)
    @patch("utilities.storage.artifactory_credentials")
    def test_create_dv_creates_only_missing_secret(
        self,
        mock_artifactory_credentials,
        mock_excluded,
        mock_validate,
        mock_data_volume_class,
        mock_wffc,
    ):
        credentials = self._credentials(secret_name="created-secret")
        mock_client = MagicMock()
        mock_artifactory_credentials.side_effect = lambda **kwargs: self._artifactory_cm(credentials)
        self._mock_data_volume(mock_data_volume_class)

        with create_dv(
            dv_name="test-dv",
            namespace="test-ns",
            client=mock_client,
            source="http",
            url="https://example.com/image.qcow2",
            use_artifactory=True,
            cert_configmap_name="existing-cm",
        ):
            pass

        mock_artifactory_credentials.assert_called_once_with(
            namespace="test-ns",
            client=mock_client,
            create_secret=True,
            create_config_map=False,
        )
        source_dict = mock_data_volume_class.call_args.kwargs["source_dict"]
        assert source_dict["http"]["secretRef"] == "created-secret"
        assert source_dict["http"]["certConfigMap"] == "existing-cm"

    @patch("utilities.storage.sc_volume_binding_mode_is_wffc", return_value=False)
    @patch("utilities.storage.DataVolume")
    @patch("utilities.storage.validate_file_exists_in_url")
    @patch("utilities.infra.url_excluded_from_validation", return_value=True)
    @patch("utilities.storage.artifactory_credentials")
    def test_create_dv_creates_only_missing_config_map(
        self,
        mock_artifactory_credentials,
        mock_excluded,
        mock_validate,
        mock_data_volume_class,
        mock_wffc,
    ):
        credentials = self._credentials(config_map_name="created-cm")
        mock_client = MagicMock()
        mock_artifactory_credentials.side_effect = lambda **kwargs: self._artifactory_cm(credentials)
        self._mock_data_volume(mock_data_volume_class)

        with create_dv(
            dv_name="test-dv",
            namespace="test-ns",
            client=mock_client,
            source="http",
            url="https://example.com/image.qcow2",
            use_artifactory=True,
            secret_name="existing-secret",
        ):
            pass

        mock_artifactory_credentials.assert_called_once_with(
            namespace="test-ns",
            client=mock_client,
            create_secret=False,
            create_config_map=True,
        )
        source_dict = mock_data_volume_class.call_args.kwargs["source_dict"]
        assert source_dict["http"]["secretRef"] == "existing-secret"
        assert source_dict["http"]["certConfigMap"] == "created-cm"

    @patch("utilities.storage.sc_volume_binding_mode_is_wffc", return_value=False)
    @patch("utilities.storage.DataVolume")
    @patch("utilities.storage.validate_file_exists_in_url")
    @patch("utilities.infra.url_excluded_from_validation", return_value=True)
    @patch("utilities.storage.artifactory_credentials")
    def test_create_dv_skips_artifactory_when_both_names_provided(
        self,
        mock_artifactory_credentials,
        mock_excluded,
        mock_validate,
        mock_data_volume_class,
        mock_wffc,
    ):
        self._mock_data_volume(mock_data_volume_class)

        with create_dv(
            dv_name="test-dv",
            namespace="test-ns",
            client=MagicMock(),
            source="http",
            url="https://example.com/image.qcow2",
            use_artifactory=True,
            secret_name="existing-secret",
            cert_configmap_name="existing-cm",
        ):
            pass

        mock_artifactory_credentials.assert_not_called()
        source_dict = mock_data_volume_class.call_args.kwargs["source_dict"]
        assert source_dict["http"]["secretRef"] == "existing-secret"
        assert source_dict["http"]["certConfigMap"] == "existing-cm"

    @patch("utilities.storage.sc_volume_binding_mode_is_wffc", return_value=False)
    @patch("utilities.storage.DataVolume")
    @patch("utilities.storage.validate_file_exists_in_url")
    @patch("utilities.infra.url_excluded_from_validation", return_value=True)
    @patch("utilities.storage.artifactory_credentials")
    def test_create_dv_unwinds_artifactory_on_data_volume_failure(
        self,
        mock_artifactory_credentials,
        mock_excluded,
        mock_validate,
        mock_data_volume_class,
        mock_wffc,
    ):
        credentials = self._credentials()
        exit_mock = MagicMock(return_value=None)

        @contextmanager
        def artifactory_cm(**kwargs):
            try:
                yield credentials
            finally:
                exit_mock()

        mock_artifactory_credentials.side_effect = artifactory_cm
        mock_data_volume_class.side_effect = RuntimeError("DV create failed")

        with pytest.raises(RuntimeError, match="DV create failed"):
            with create_dv(
                dv_name="test-dv",
                namespace="test-ns",
                client=MagicMock(),
                source="http",
                url="https://example.com/image.qcow2",
                use_artifactory=True,
            ):
                pass

        exit_mock.assert_called_once()
