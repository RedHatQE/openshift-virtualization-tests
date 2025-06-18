import os

import pytest
from ocp_resources.resource import get_client

from utilities.constants import REMOTE_KUBECONFIG


@pytest.fixture(scope="session")
def remote_kubeconfig_export_path():
    return os.environ.get(REMOTE_KUBECONFIG)


@pytest.fixture(scope="session")
def remote_admin_client(remote_kubeconfig_export_path):
    """
    Get DynamicClient for a remote cluster
    """
    return get_client(config_file=remote_kubeconfig_export_path)
