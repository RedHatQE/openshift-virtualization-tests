import logging

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.namespace import Namespace

from utilities.constants.namespaces import NamespacesNames

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def nmstate_namespace(admin_client):
    try:
        return Namespace(client=admin_client, name=NamespacesNames.OPENSHIFT_NMSTATE, ensure_exists=True)

    except ResourceNotFoundError:
        LOGGER.info(f"Namespace '{NamespacesNames.OPENSHIFT_NMSTATE}' not found.")
        return None


@pytest.fixture(scope="session")
def nmstate_dependent_placeholder():
    """
    Placeholder fixture that serves as a dependency marker for fixtures that interact
    with NMState Custom Resources (NNCP, NNCE, NNS).

    This fixture is used by pytest_collection_modifyitems to automatically detect
    and mark tests that depend on NMState functionality.
    """
    return
