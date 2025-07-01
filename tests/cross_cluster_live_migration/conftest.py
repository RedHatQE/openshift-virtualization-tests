import os

import pytest
from ocp_resources.resource import get_client

from utilities.constants import REMOTE_KUBECONFIG


@pytest.fixture(scope="session")
def remote_kubeconfig_export_path():
    """
    Resolve path to the remote cluster kubeconfig.
    Fail if the environment variable is not provided or file doesn't exist.
    """
    path = os.environ.get(REMOTE_KUBECONFIG)
    if not path:
        raise ValueError(f"{REMOTE_KUBECONFIG} environment variable is not set")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Remote kubeconfig file not found at '{path}'")
    return path


@pytest.fixture(scope="session") 
def remote_admin_client(remote_kubeconfig_export_path): # skip-unused-code
    """
    Get DynamicClient for a remote cluster
    """
    return get_client(config_file=remote_kubeconfig_export_path)
