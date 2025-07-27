import logging
import os

import pytest
from ocp_resources.resource import get_client

from utilities.constants import REMOTE_KUBECONFIG

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def remote_kubeconfig_export_path(request):
    """
    Resolve path to the remote cluster kubeconfig.
    First check for CLI argument, then fall back to environment variable.
    Fail if neither is provided or file does not exist.
    """
    path = request.session.config.getoption("--remote-kubeconfig") or os.environ.get(REMOTE_KUBECONFIG)

    if not path:
        raise ValueError(
            f"Remote kubeconfig path not provided. Use --remote-kubeconfig CLI argument "
            f"or set {REMOTE_KUBECONFIG} environment variable"
        )

    if not os.path.isfile(path):
        raise FileNotFoundError(f"Remote kubeconfig file not found at '{path}'")

    LOGGER.info(f"Remote kubeconfig path: {path}")
    return path


@pytest.fixture(scope="session")
def remote_admin_client(remote_kubeconfig_export_path):  # skip-unused-code
    """
    Get DynamicClient for a remote cluster
    """
    return get_client(config_file=remote_kubeconfig_export_path)
