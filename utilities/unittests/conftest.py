"""Pytest configuration for utilities tests - independent of main project"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ["OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH"] = "x86_64"

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock get_client to prevent K8s API calls
from ocp_resources import resource  # noqa: E402

resource.get_client = lambda: MagicMock()

# Create mock modules to break circular imports
sys.modules["utilities.data_collector"] = MagicMock()
sys.modules["utilities.data_collector"].get_data_collector_base_directory = lambda: "/tmp/data"  # type: ignore
sys.modules["utilities.data_collector"].collect_alerts_data = MagicMock()  # type: ignore


# Mock fixtures for common dependencies
@pytest.fixture(autouse=True)
def mock_get_client(monkeypatch):
    """Auto-mock get_client for all tests"""
    mock_client = MagicMock()
    monkeypatch.setattr("ocp_resources.resource.get_client", lambda: mock_client)
    return mock_client


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

    # Save original getLogger
    original_get_logger = logging.getLogger

    # Create a mock logger that returns a real logger with mock handlers
    def mock_get_logger(name=None):
        logger = original_get_logger(name)  # noqa: FCN001
        # Clear any existing handlers
        logger.handlers = []
        # Add a mock handler with proper level attribute
        mock_handler = MagicMock()
        mock_handler.level = logging.INFO
        logger.addHandler(mock_handler)  # noqa: FCN001
        return logger

    # Patch getLogger
    logging.getLogger = mock_get_logger

    yield

    # Restore original getLogger
    logging.getLogger = original_get_logger
