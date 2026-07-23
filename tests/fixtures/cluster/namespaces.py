"""Cluster namespace fixtures."""

import logging
import pathlib

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.namespace import Namespace

from utilities.constants.cluster import POD_SECURITY_NAMESPACE_LABELS
from utilities.constants.namespaces import NamespacesNames
from utilities.infra import create_ns, generate_namespace_name
from utilities.pytest_utils import exit_pytest_execution

LOGGER = logging.getLogger(__name__)

# Path to the `tests/` directory, used to derive per-test namespace names.
_TESTS_DIR = str(pathlib.Path(__file__).parent.parent.parent)


@pytest.fixture(scope="module")
def namespace(request, admin_client, unprivileged_client):
    """
    To create namespace using admin client, pass {"use_unprivileged_client": False} to request.param
    (default for "use_unprivileged_client" is True)
    """
    use_unprivileged_client = getattr(request, "param", {}).get("use_unprivileged_client", True)
    teardown = getattr(request, "param", {}).get("teardown", True)
    unprivileged_client = unprivileged_client if use_unprivileged_client else None
    yield from create_ns(
        unprivileged_client=unprivileged_client,
        admin_client=admin_client,
        name=generate_namespace_name(file_path=request.fspath.strpath.split(f"{_TESTS_DIR}/")[1]),
        teardown=teardown,
    )


@pytest.fixture(scope="session")
def cnv_tests_utilities_namespace(admin_client, installing_cnv):
    if installing_cnv:
        yield
    else:
        name = NamespacesNames.CNV_TESTS_UTILITIES
        if Namespace(client=admin_client, name=name).exists:
            exit_pytest_execution(
                log_message=f"{name} namespace already exists."
                f"\nAfter verifying no one else is performing tests against the cluster, run:"
                f"\n'oc delete namespace {name}'",
                return_code=100,
                message=f"{name} namespace already exists.",
                filename="cnv_tests_utilities_ns_failure.txt",
                admin_client=admin_client,
            )

        else:
            yield from create_ns(
                admin_client=admin_client,
                labels=POD_SECURITY_NAMESPACE_LABELS,
                name=name,
            )


@pytest.fixture(scope="session")
def kube_system_namespace():
    kube_system_ns = Namespace(name="kube-system")
    if kube_system_ns.exists:
        return kube_system_ns
    raise ResourceNotFoundError(f"{kube_system_ns.name} namespace not found")


@pytest.fixture(scope="session")
def nmstate_namespace(admin_client):
    try:
        return Namespace(client=admin_client, name=NamespacesNames.OPENSHIFT_NMSTATE, ensure_exists=True)

    except ResourceNotFoundError:
        LOGGER.info(f"Namespace '{NamespacesNames.OPENSHIFT_NMSTATE}' not found.")
        return None
