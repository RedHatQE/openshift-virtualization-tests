# Generated using Claude cli

"""Unit tests for pytest_utils module"""

from unittest.mock import MagicMock, patch

# Circular dependencies are already mocked in conftest.py
from utilities.pytest_utils import get_cnv_version_explorer_url


class TestGetCnvVersionExplorerUrl:
    @patch("utilities.pytest_utils.os.environ", {"CNV_VERSION_EXPLORER_URL": "https://version-explorer.com"})
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_cnv_version_explorer_url_install_flag(self, mock_logger):
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda option: option == "install"
        assert get_cnv_version_explorer_url(mock_config) == "https://version-explorer.com"

    @patch("utilities.pytest_utils.os.environ", {"CNV_VERSION_EXPLORER_URL": "https://version-explorer.com"})
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_cnv_version_explorer_url_cnv_upgrade(self, mock_logger):
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda option: {"install": False, "upgrade": "cnv"}.get(option, False)
        assert get_cnv_version_explorer_url(mock_config) == "https://version-explorer.com"

    @patch("utilities.pytest_utils.os.environ", {"CNV_VERSION_EXPLORER_URL": "https://version-explorer.com"})
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_cnv_version_explorer_url_eus_upgrade(self, mock_logger):
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda option: {"install": False, "upgrade": "eus"}.get(option, False)
        assert get_cnv_version_explorer_url(mock_config) == "https://version-explorer.com"

    @patch("utilities.pytest_utils.os.environ", {"CNV_VERSION_EXPLORER_URL": "https://version-explorer.com"})
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_cnv_version_explorer_url_upgrade_custom_cnv(self, mock_logger):
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda option: {
            "install": False,
            "upgrade": None,
            "upgrade_custom": "cnv",
        }.get(option, False)
        assert get_cnv_version_explorer_url(mock_config) == "https://version-explorer.com"

    @patch("utilities.pytest_utils.os.environ", {"CNV_VERSION_EXPLORER_URL": "https://version-explorer.com"})
    @patch("utilities.pytest_utils.LOGGER")
    def test_get_cnv_version_explorer_url_upgrade_custom_eus(self, mock_logger):
        mock_config = MagicMock()
        mock_config.getoption.side_effect = lambda option: {
            "install": False,
            "upgrade": None,
            "upgrade_custom": "eus",
        }.get(option, False)
        assert get_cnv_version_explorer_url(mock_config) == "https://version-explorer.com"
