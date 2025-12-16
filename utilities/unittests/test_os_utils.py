# Generated using Claude cli

"""Unit tests for os_utils module"""

from unittest.mock import MagicMock, patch

import pytest

from utilities.exceptions import OsDictNotFoundError
from utilities.os_utils import (
    CENTOS_OS_MAPPING,
    FEDORA_OS_MAPPING,
    RHEL_OS_MAPPING,
    WINDOWS_OS_MAPPING,
    generate_latest_os_dict,
    generate_linux_instance_type_os_matrix,
    generate_os_matrix_dict,
    get_windows_container_disk_path,
)


class TestGetWindowsContainerDiskPath:
    """Test cases for get_windows_container_disk_path function"""

    @patch("utilities.os_utils.Images")
    def test_get_windows_container_disk_path_win10(self, mock_images):
        """Test generating container disk path for win10"""
        mock_images.Windows.DOCKER_IMAGE_DIR = "quay.io/test"

        result = get_windows_container_disk_path(os_value="win10")

        assert result == "quay.io/test/windows10-container-disk:4.99"

    @patch("utilities.os_utils.Images")
    def test_get_windows_container_disk_path_win2k19(self, mock_images):
        """Test generating container disk path for win2k19"""
        mock_images.Windows.DOCKER_IMAGE_DIR = "quay.io/test"

        result = get_windows_container_disk_path(os_value="win2k19")

        assert result == "quay.io/test/windows2k19-container-disk:4.99"

    @patch("utilities.os_utils.Images")
    def test_get_windows_container_disk_path_win2k22(self, mock_images):
        """Test generating container disk path for win2k22"""
        mock_images.Windows.DOCKER_IMAGE_DIR = "quay.io/test"

        result = get_windows_container_disk_path(os_value="win2k22")

        assert result == "quay.io/test/windows2k22-container-disk:4.99"

    @patch("utilities.os_utils.Images")
    def test_get_windows_container_disk_path_win11(self, mock_images):
        """Test generating container disk path for win11"""
        mock_images.Windows.DOCKER_IMAGE_DIR = "quay.io/test"

        result = get_windows_container_disk_path(os_value="win11")

        assert result == "quay.io/test/windows11-container-disk:4.99"

    def test_get_windows_container_disk_path_invalid_os(self):
        """Test error when os_value doesn't start with 'win'"""
        with pytest.raises(ValueError, match="os_value must start with 'win'"):
            get_windows_container_disk_path(os_value="linux")

    def test_get_windows_container_disk_path_rhel_raises(self):
        """Test error when os_value is rhel"""
        with pytest.raises(ValueError, match="os_value must start with 'win'"):
            get_windows_container_disk_path(os_value="rhel9")


class TestGenerateOsMatrixDict:
    """Test cases for generate_os_matrix_dict function"""

    @patch("utilities.os_utils.Images")
    def test_generate_rhel_os_matrix_single_version(self, mock_images, mock_os_images):
        """Test RHEL OS matrix generation with single version"""
        mock_images.Rhel = mock_os_images["rhel"]

        result = generate_os_matrix_dict(os_name="rhel", supported_operating_systems=["rhel-9-5"])

        assert len(result) == 1
        assert "rhel-9-5" in result[0]
        rhel_config = result[0]["rhel-9-5"]
        assert rhel_config["os_version"] == "9.5"
        assert rhel_config["image_name"] == "rhel-9.5.qcow2"
        assert rhel_config["image_path"] == "cnv-tests/rhel-images/rhel-9.5.qcow2"
        assert rhel_config["dv_size"] == "20Gi"
        assert rhel_config["template_labels"]["os"] == "rhel9.5"
        assert rhel_config["template_labels"]["workload"] == "server"
        assert rhel_config["template_labels"]["flavor"] == "tiny"
        assert "latest_release" not in rhel_config

    @patch("utilities.os_utils.Images")
    def test_generate_rhel_os_matrix_multiple_versions(self, mock_images, mock_os_images):
        """Test RHEL OS matrix generation with multiple versions"""
        mock_images.Rhel = mock_os_images["rhel"]

        result = generate_os_matrix_dict(os_name="rhel", supported_operating_systems=["rhel-8-10", "rhel-9-6"])

        assert len(result) == 2

        # Check RHEL 8.10
        rhel_810 = next(item for item in result if "rhel-8-10" in item)["rhel-8-10"]
        assert rhel_810["os_version"] == "8.10"
        assert rhel_810["image_name"] == "rhel-8.10.qcow2"

        # Check RHEL 9.6 (latest)
        rhel_96 = next(item for item in result if "rhel-9-6" in item)["rhel-9-6"]
        assert rhel_96["os_version"] == "9.6"
        assert rhel_96["image_name"] == "rhel-9.6.qcow2"
        assert rhel_96["latest_released"] is True

    @patch("utilities.os_utils.Images")
    def test_generate_windows_os_matrix_with_uefi(self, mock_images, mock_os_images):
        """Test Windows OS matrix generation with UEFI support"""
        mock_images.Windows = mock_os_images["windows"]

        result = generate_os_matrix_dict(os_name="windows", supported_operating_systems=["win-10", "win-2019"])

        assert len(result) == 2

        # Check Windows 10 (UEFI + desktop workload)
        win10 = next(item for item in result if "win-10" in item)["win-10"]
        assert win10["os_version"] == "10"
        assert win10["image_name"] == "win10.qcow2"
        assert win10["image_path"] == "cnv-tests/windows-uefi-images/win10.qcow2"
        assert win10["template_labels"]["workload"] == "desktop"
        assert win10["template_labels"]["flavor"] == "medium"

        # Check Windows 2019 (UEFI + server workload)
        win2019 = next(item for item in result if "win-2019" in item)["win-2019"]
        assert win2019["image_path"] == "cnv-tests/windows-uefi-images/win2k19.qcow2"
        assert win2019["template_labels"]["workload"] == "server"

    @patch("utilities.os_utils.Images")
    def test_generate_windows_os_matrix_without_uefi(self, mock_images, mock_os_images):
        """Test Windows OS matrix generation without UEFI"""
        mock_images.Windows = mock_os_images["windows"]

        result = generate_os_matrix_dict(os_name="windows", supported_operating_systems=["win-2022"])

        assert len(result) == 1
        win2022 = result[0]["win-2022"]
        assert win2022["image_path"] == "cnv-tests/windows-images/win2022.qcow2"

    @patch("utilities.os_utils.Images")
    def test_generate_fedora_os_matrix(self, mock_images, mock_os_images):
        """Test Fedora OS matrix generation"""
        mock_images.Fedora = mock_os_images["fedora"]

        result = generate_os_matrix_dict(os_name="fedora", supported_operating_systems=["fedora-43"])

        assert len(result) == 1
        fedora_config = result[0]["fedora-43"]
        assert fedora_config["os_version"] == "43"
        assert fedora_config["image_name"] == "fedora-43.qcow2"
        assert fedora_config["template_labels"]["workload"] == "server"
        assert fedora_config["template_labels"]["flavor"] == "small"
        assert fedora_config["latest_released"] is True

    @patch("utilities.os_utils.Images")
    def test_generate_centos_os_matrix(self, mock_images, mock_os_images):
        """Test CentOS OS matrix generation"""
        mock_images.Centos = mock_os_images["centos"]

        result = generate_os_matrix_dict(os_name="centos", supported_operating_systems=["centos-stream-9"])

        assert len(result) == 1
        centos_config = result[0]["centos-stream-9"]
        assert centos_config["os_version"] == "9"
        assert centos_config["image_name"] == "centos-stream-9.qcow2"
        assert centos_config["template_labels"]["os"] == "centos-stream9"

    def test_generate_os_matrix_unsupported_os(self):
        """Test error handling for unsupported OS"""
        with pytest.raises(ValueError, match="Unsupported OS: ubuntu"):
            generate_os_matrix_dict(os_name="ubuntu", supported_operating_systems=["ubuntu-20-04"])

    def test_generate_os_matrix_empty_supported_versions(self, mock_os_images):
        """Test error handling for unsupported OS versions"""
        with patch("utilities.os_utils.Images") as mock_images:
            mock_images.Rhel = mock_os_images["rhel"]

            with pytest.raises(ValueError, match="Unsupported OS versions: \\['rhel-6-1'\\] for rhel"):
                generate_os_matrix_dict(os_name="rhel", supported_operating_systems=["rhel-6-1"])

    @patch("utilities.os_utils.Images")
    def test_generate_os_matrix_missing_images_class(self, mock_images):
        """Test error handling when Images class is missing for OS"""
        # Remove the Rhel attribute to simulate missing class
        del mock_images.Rhel
        mock_images.Rhel = None

        with pytest.raises(ValueError, match="Unsupported OS: rhel.*Make sure it is supported"):
            generate_os_matrix_dict(os_name="rhel", supported_operating_systems=["rhel-9-5"])

    @patch("utilities.os_utils.Images")
    def test_generate_os_matrix_missing_latest_release(self, mock_images, mock_os_images):
        """Test error handling when LATEST_RELEASE_STR is missing"""
        mock_class = MagicMock()
        mock_class.DEFAULT_DV_SIZE = "20Gi"
        # Missing LATEST_RELEASE_STR
        del mock_class.LATEST_RELEASE_STR
        mock_images.Rhel = mock_class

        with pytest.raises(ValueError, match="rhel is missing `LATEST_RELEASE_STR` attribute"):
            generate_os_matrix_dict(os_name="rhel", supported_operating_systems=["rhel-9-5"])

    @patch("utilities.os_utils.Images")
    def test_generate_os_matrix_missing_default_dv_size(self, mock_images, mock_os_images):
        """Test error handling when DEFAULT_DV_SIZE is missing"""
        mock_class = MagicMock()
        mock_class.LATEST_RELEASE_STR = "rhel-9.6.qcow2"
        # Missing DEFAULT_DV_SIZE
        del mock_class.DEFAULT_DV_SIZE
        mock_images.Rhel = mock_class

        with pytest.raises(ValueError, match="rhel is missing `DEFAULT_DV_SIZE` attribute"):
            generate_os_matrix_dict(os_name="rhel", supported_operating_systems=["rhel-9-5"])

    @patch("utilities.os_utils.Images")
    def test_generate_os_matrix_missing_image_attribute(self, mock_images, mock_os_images):
        """Test error handling when image attribute is missing"""
        mock_class = MagicMock()
        mock_class.LATEST_RELEASE_STR = "rhel-9.6.qcow2"
        mock_class.DEFAULT_DV_SIZE = "20Gi"
        # Missing RHEL9_5_IMG
        del mock_class.RHEL9_5_IMG
        mock_images.Rhel = mock_class

        with pytest.raises(ValueError, match="rhel is missing RHEL9_5_IMG attribute"):
            generate_os_matrix_dict(os_name="rhel", supported_operating_systems=["rhel-9-5"])

    @patch("utilities.os_utils.Images")
    def test_generate_os_matrix_missing_dir_attribute(self, mock_images, mock_os_images):
        """Test error handling when DIR attribute is missing"""
        mock_class = MagicMock()
        mock_class.LATEST_RELEASE_STR = "rhel-9.6.qcow2"
        mock_class.DEFAULT_DV_SIZE = "20Gi"
        mock_class.RHEL9_5_IMG = "rhel-9.5.qcow2"
        # Missing DIR
        del mock_class.DIR
        mock_images.Rhel = mock_class

        with pytest.raises(ValueError, match="rhel is missing `DIR` attribute"):
            generate_os_matrix_dict(os_name="rhel", supported_operating_systems=["rhel-9-5"])

    @patch("utilities.os_utils.Images")
    def test_generate_os_matrix_missing_uefi_dir_attribute(self, mock_images, mock_os_images):
        """Test error handling when UEFI_WIN_DIR attribute is missing for UEFI Windows"""
        mock_class = MagicMock()
        mock_class.LATEST_RELEASE_STR = "win2k25.qcow2"
        mock_class.DEFAULT_DV_SIZE = "60Gi"
        mock_class.WIN10_IMG = "win10.qcow2"
        # Missing UEFI_WIN_DIR
        del mock_class.UEFI_WIN_DIR
        mock_images.Windows = mock_class

        with pytest.raises(ValueError, match="windows is missing `UEFI_WIN_DIR` attribute"):
            generate_os_matrix_dict(os_name="windows", supported_operating_systems=["win-10"])

    @patch("utilities.os_utils.ArchImages")
    @patch("utilities.os_utils.Images")
    def test_generate_os_matrix_dict_with_arch_adds_architecture_labels(
        self, mock_images, mock_arch_images, mock_os_images
    ):
        """Test that passing arch adds architecture to template_labels and data source suffix"""
        mock_images.Rhel = mock_os_images["rhel"]
        # When arch is set, getattr(ArchImages, "AMD64") is used
        mock_arch_images.AMD64 = mock_os_images["rhel"]

        result = generate_os_matrix_dict(
            os_name="rhel",
            supported_operating_systems=["rhel-9-5"],
            arch="amd64",
        )

        assert len(result) == 1
        rhel_config = result[0]["rhel-9-5"]
        assert rhel_config["template_labels"]["architecture"] == "amd64"
        assert rhel_config["data_source"] == "rhel9-amd64"


class TestGenerateInstanceTypeRhelOsMatrix:
    """Test cases for generate_linux_instance_type_os_matrix function"""

    def test_generate_instance_type_single_preference(self):
        """Test instance type matrix generation with single preference"""
        result = generate_linux_instance_type_os_matrix("rhel", ["rhel-9"])

        assert len(result) == 1
        assert "rhel-9" in result[0]
        config = result[0]["rhel-9"]
        assert config["preference"] == "rhel-9"
        assert config["DATA_SOURCE_NAME"] == "rhel9"
        assert config["latest_released"] is True

    def test_generate_instance_type_multiple_preferences(self):
        """Test instance type matrix generation with multiple preferences"""
        preferences = ["rhel-8", "rhel-9", "rhel-7"]
        result = generate_linux_instance_type_os_matrix("rhel", preferences)

        assert len(result) == 3

        # Check all preferences are present
        pref_names = [list(item.keys())[0] for item in result]
        assert set(pref_names) == {"rhel-8", "rhel-9", "rhel-7"}

        # Check that latest RHEL (9) has latest_released flag
        rhel9_item = next(item for item in result if "rhel-9" in item)
        assert rhel9_item["rhel-9"]["latest_released"] is True

        # Check that older versions don't have latest_released flag
        rhel8_item = next(item for item in result if "rhel-8" in item)
        assert "latest_released" not in rhel8_item["rhel-8"]

        rhel7_item = next(item for item in result if "rhel-7" in item)
        assert "latest_released" not in rhel7_item["rhel-7"]

    def test_generate_instance_type_preference_format(self):
        """Test preference string formatting"""
        result = generate_linux_instance_type_os_matrix("rhel", ["rhel-8"])

        config = result[0]["rhel-8"]
        assert config["preference"] == "rhel-8"  # Preference stored as-is
        assert config["DATA_SOURCE_NAME"] == "rhel8"  # Dash removed

    def test_generate_instance_type_complex_versions(self):
        """Test with complex version numbers"""
        preferences = ["rhel-8", "rhel-9", "rhel-10"]
        result = generate_linux_instance_type_os_matrix("rhel", preferences)

        # RHEL-10 should be identified as latest (highest number)
        rhel10_item = next(item for item in result if "rhel-10" in item)
        assert rhel10_item["rhel-10"]["latest_released"] is True

        # Other versions should not have latest_released
        rhel9_item = next(item for item in result if "rhel-9" in item)
        assert "latest_released" not in rhel9_item["rhel-9"]

    def test_generate_instance_type_single_digit_versions(self):
        """Test with single digit version numbers"""
        preferences = ["rhel-7", "rhel-8", "rhel-9"]
        result = generate_linux_instance_type_os_matrix("rhel", preferences)

        # RHEL-9 should be latest
        rhel9_item = next(item for item in result if "rhel-9" in item)
        assert rhel9_item["rhel-9"]["latest_released"] is True


class TestOsMappingsConstants:
    """Test cases for OS mapping constants"""

    def test_rhel_os_mapping_structure(self):
        """Test RHEL OS mapping has correct structure"""
        assert "workload" in RHEL_OS_MAPPING
        assert "flavor" in RHEL_OS_MAPPING
        assert "rhel-8-10" in RHEL_OS_MAPPING
        assert "rhel-9-5" in RHEL_OS_MAPPING
        assert "rhel-9-6" in RHEL_OS_MAPPING

        # Check required keys in version entries
        for version_key in ["rhel-8-10", "rhel-9-5", "rhel-9-6"]:
            version_data = RHEL_OS_MAPPING[version_key]
            assert "image_name" in version_data
            assert "os_version" in version_data
            assert "os" in version_data

    def test_windows_os_mapping_structure(self):
        """Test Windows OS mapping has correct structure"""
        assert "workload" in WINDOWS_OS_MAPPING
        assert "flavor" in WINDOWS_OS_MAPPING

        # Check for UEFI flag where expected
        assert WINDOWS_OS_MAPPING["win-10"]["uefi"] is True
        assert WINDOWS_OS_MAPPING["win-2019"]["uefi"] is True
        assert "uefi" not in WINDOWS_OS_MAPPING["win-2022"]

    def test_fedora_os_mapping_structure(self):
        """Test Fedora OS mapping has correct structure"""
        assert "workload" in FEDORA_OS_MAPPING
        assert "flavor" in FEDORA_OS_MAPPING
        assert "fedora-43" in FEDORA_OS_MAPPING

    def test_centos_os_mapping_structure(self):
        """Test CentOS OS mapping has correct structure"""
        assert "workload" in CENTOS_OS_MAPPING
        assert "flavor" in CENTOS_OS_MAPPING
        assert "centos-stream-9" in CENTOS_OS_MAPPING


class TestGenerateLatestOsDict:
    """Test cases for generate_latest_os_dict function"""

    def test_returns_latest_os_dict_when_found(self):
        """Test returning the OS dict marked as latest_released"""
        os_matrix = [
            {"rhel-8-10": {"os_version": "8.10", "image_name": "rhel-8.10.qcow2"}},
            {"rhel-9-6": {"os_version": "9.6", "image_name": "rhel-9.6.qcow2", "latest_released": True}},
        ]

        result = generate_latest_os_dict(os_matrix=os_matrix)

        assert result == {"os_version": "9.6", "image_name": "rhel-9.6.qcow2", "latest_released": True}

    def test_returns_latest_os_dict_from_first_position(self):
        """Test finding latest_released when it's in the first matrix entry"""
        os_matrix = [
            {"fedora-43": {"os_version": "43", "latest_released": True}},
            {"fedora-42": {"os_version": "42"}},
        ]

        result = generate_latest_os_dict(os_matrix=os_matrix)

        assert result == {"os_version": "43", "latest_released": True}

    def test_returns_latest_os_dict_from_middle_position(self):
        """Test finding latest_released when it's in a middle matrix entry"""
        os_matrix = [
            {"rhel-7-9": {"os_version": "7.9"}},
            {"rhel-9-6": {"os_version": "9.6", "latest_released": True}},
            {"rhel-8-10": {"os_version": "8.10"}},
        ]

        result = generate_latest_os_dict(os_matrix=os_matrix)

        assert result == {"os_version": "9.6", "latest_released": True}

    def test_raises_error_when_no_latest_released(self):
        """Test raising OsDictNotFoundError when no OS is marked as latest_released"""
        os_matrix = [
            {"rhel-8-10": {"os_version": "8.10"}},
            {"rhel-9-5": {"os_version": "9.5"}},
        ]

        with pytest.raises(OsDictNotFoundError, match="No OS is marked as 'latest_released'"):
            generate_latest_os_dict(os_matrix=os_matrix)

    def test_raises_error_on_empty_list(self):
        """Test raising OsDictNotFoundError when os_matrix is empty"""
        with pytest.raises(OsDictNotFoundError, match="No OS is marked as 'latest_released'"):
            generate_latest_os_dict(os_matrix=[])

    def test_returns_first_latest_when_multiple_marked(self):
        """Test returning the first latest_released when multiple OS dicts are marked"""
        os_matrix = [
            {"rhel-8-10": {"os_version": "8.10", "latest_released": True}},
            {"rhel-9-6": {"os_version": "9.6", "latest_released": True}},
        ]

        result = generate_latest_os_dict(os_matrix=os_matrix)

        assert result["os_version"] == "8.10"

    def test_handles_complex_os_matrix_structure(self):
        """Test with full OS matrix structure including all fields"""
        os_matrix = [
            {
                "win-2022": {
                    "os_version": "2022",
                    "image_name": "win2022.qcow2",
                    "image_path": "cnv-tests/windows-images/win2022.qcow2",
                    "dv_size": "60Gi",
                    "template_labels": {"os": "win2k22", "workload": "server", "flavor": "medium"},
                    "data_source": "win2k22",
                }
            },
            {
                "win-2025": {
                    "os_version": "2025",
                    "image_name": "win2k25.qcow2",
                    "image_path": "cnv-tests/windows-uefi-images/win2k25.qcow2",
                    "dv_size": "60Gi",
                    "template_labels": {"os": "win2k25", "workload": "server", "flavor": "medium"},
                    "data_source": "win2k25",
                    "latest_released": True,
                }
            },
        ]

        result = generate_latest_os_dict(os_matrix=os_matrix)

        assert result["os_version"] == "2025"
        assert result["image_name"] == "win2k25.qcow2"
        assert result["latest_released"] is True

    def test_handles_latest_released_false_value(self):
        """Test that latest_released=False is not treated as latest"""
        os_matrix = [
            {"rhel-8-10": {"os_version": "8.10", "latest_released": False}},
            {"rhel-9-6": {"os_version": "9.6", "latest_released": True}},
        ]

        result = generate_latest_os_dict(os_matrix=os_matrix)

        assert result["os_version"] == "9.6"

    def test_raises_error_when_all_latest_released_false(self):
        """Test raising OsDictNotFoundError when all latest_released values are False"""
        os_matrix = [
            {"rhel-8-10": {"os_version": "8.10", "latest_released": False}},
            {"rhel-9-5": {"os_version": "9.5", "latest_released": False}},
        ]

        with pytest.raises(OsDictNotFoundError, match="No OS is marked as 'latest_released'"):
            generate_latest_os_dict(os_matrix=os_matrix)
