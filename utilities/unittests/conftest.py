# Generated using Claude cli

"""Pytest configuration for utilities tests - independent of main project"""

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from ocp_resources import resource

import utilities

os.environ["OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH"] = "x86_64"

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock get_client to prevent K8s API calls


def _mock_get_client(*args: Any, **kwargs: Any) -> MagicMock:  # type: ignore[misc]
    return MagicMock()


resource.get_client = _mock_get_client  # type: ignore[assignment]

# Create mock modules to break circular imports
# Set up mock modules before any imports
# Note: utilities.hco is mocked here but test_hco.py will clear it and import real module
mock_hco = MagicMock()
mock_infra = MagicMock()
mock_data_collector = MagicMock()
mock_data_collector.get_data_collector_base_directory = MagicMock(return_value="/tmp/data")
mock_data_collector.get_data_collector_base = MagicMock(return_value="/tmp/data/")

# Mock jira package to prevent import conflicts
mock_jira = MagicMock()
mock_jira.JIRA = MagicMock()

sys.modules["utilities.hco"] = mock_hco
sys.modules["utilities.infra"] = mock_infra
sys.modules["utilities.data_collector"] = mock_data_collector
sys.modules["jira"] = mock_jira

# Also set them as attributes of the utilities module for tests that need them
utilities.hco = mock_hco  # type: ignore[attr-defined]
utilities.infra = mock_infra  # type: ignore[attr-defined]
utilities.data_collector = mock_data_collector  # type: ignore[attr-defined]


# Mock fixtures for common dependencies
@pytest.fixture(autouse=True)
def setup_py_config():
    """Setup py_config for tests that need data_collector configuration"""
    from pytest_testconfig import config as py_config

    # Ensure data_collector config is set up
    if "data_collector" not in py_config:
        py_config["data_collector"] = {"data_collector_base_directory": "/tmp/data"}

    yield


@pytest.fixture(autouse=True)
def mock_data_collector_base_directory():
    """Auto-mock get_data_collector_base_directory for all tests"""
    with patch("utilities.data_collector.get_data_collector_base_directory", return_value="/tmp/data"):
        yield "/tmp/data"


@pytest.fixture
def mock_node():
    """Mock Node resource"""
    node = MagicMock()
    node.name = "test-node"
    node.labels = {"kubernetes.io/arch": "x86_64"}
    node.status = {"conditions": []}
    return node


@pytest.fixture
def mock_vm():
    """Mock VirtualMachine resource"""
    vm = MagicMock()
    vm.name = "test-vm"
    vm.namespace = "test-namespace"
    vm.status = "Running"
    vm.instance = MagicMock()
    vm.username = "test-user"
    vm.password = "test-pass"
    vm.login_params = {}
    return vm


@pytest.fixture
def mock_vm_with_login_params():
    """Mock VirtualMachine resource with login_params"""
    vm = MagicMock()
    vm.name = "test-vm"
    vm.namespace = "test-namespace"
    vm.status = "Running"
    vm.instance = MagicMock()
    vm.username = "default-user"
    vm.password = "default-pass"
    vm.login_params = {
        "username": "login-user",
        "password": "login-pass",
    }
    return vm


@pytest.fixture
def mock_vm_no_namespace():
    """Mock VirtualMachine resource without namespace"""
    vm = MagicMock()
    vm.name = "test-vm"
    vm.namespace = None
    vm.username = "test-user"
    vm.password = "test-pass"
    vm.login_params = {}
    return vm


@pytest.fixture(autouse=True)
def mock_logger():
    """Auto-mock logger for all tests to prevent logging issues"""
    import logging

    # Save original getLogger to avoid recursion
    original_get_logger = logging.getLogger

    # Create a mock logger that returns a real logger with mock handlers
    def mock_get_logger(name=None):
        logger = original_get_logger(name)
        # Clear any existing handlers
        logger.handlers = []
        # Add a mock handler with proper level attribute
        mock_handler = MagicMock()
        mock_handler.level = logging.INFO
        logger.addHandler(mock_handler)
        return logger

    with patch("logging.getLogger", side_effect=mock_get_logger):
        yield


# Shared utility functions for data_collector tests


@pytest.fixture
def mock_os_images():
    """Fixture providing mock OS image classes for testing"""
    # Mock RHEL class
    mock_rhel_class = MagicMock()
    mock_rhel_class.LATEST_RELEASE_STR = "rhel-9.6.qcow2"
    mock_rhel_class.DEFAULT_DV_SIZE = "20Gi"
    mock_rhel_class.RHEL8_10_IMG = "rhel-8.10.qcow2"
    mock_rhel_class.RHEL9_5_IMG = "rhel-9.5.qcow2"
    mock_rhel_class.RHEL9_6_IMG = "rhel-9.6.qcow2"
    mock_rhel_class.DIR = "cnv-tests/rhel-images"

    # Mock Windows class
    mock_windows_class = MagicMock()
    mock_windows_class.LATEST_RELEASE_STR = "win2k25.qcow2"
    mock_windows_class.DEFAULT_DV_SIZE = "60Gi"
    mock_windows_class.WIN10_IMG = "win10.qcow2"
    mock_windows_class.WIN11_IMG = "win11.qcow2"
    mock_windows_class.WIN2k19_IMG = "win2k19.qcow2"
    mock_windows_class.WIN2022_IMG = "win2022.qcow2"
    mock_windows_class.WIN2k25_IMG = "win2k25.qcow2"
    mock_windows_class.DIR = "cnv-tests/windows-images"
    mock_windows_class.UEFI_WIN_DIR = "cnv-tests/windows-uefi-images"

    # Mock Fedora class
    mock_fedora_class = MagicMock()
    mock_fedora_class.LATEST_RELEASE_STR = "fedora-43.qcow2"
    mock_fedora_class.DEFAULT_DV_SIZE = "20Gi"
    mock_fedora_class.FEDORA43_IMG = "fedora-43.qcow2"
    mock_fedora_class.DIR = "cnv-tests/fedora-images"

    # Mock CentOS class
    mock_centos_class = MagicMock()
    mock_centos_class.LATEST_RELEASE_STR = "centos-stream-9.qcow2"
    mock_centos_class.DEFAULT_DV_SIZE = "20Gi"
    mock_centos_class.CENTOS_STREAM_9_IMG = "centos-stream-9.qcow2"
    mock_centos_class.DIR = "cnv-tests/centos-images"

    # Mock Images container
    mock_images = MagicMock()
    mock_images.Rhel = mock_rhel_class
    mock_images.Windows = mock_windows_class
    mock_images.Fedora = mock_fedora_class
    mock_images.Centos = mock_centos_class

    return {
        "images": mock_images,
        "rhel": mock_rhel_class,
        "windows": mock_windows_class,
        "fedora": mock_fedora_class,
        "centos": mock_centos_class,
    }
