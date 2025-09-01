import logging
import os
import shlex
from copy import deepcopy

import pytest
from ocp_resources.forklift_controller import ForkliftController
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition
from ocp_resources.provider import Provider
from ocp_resources.resource import ResourceEditor, get_client
from ocp_resources.secret import Secret
from pyhelper_utils.shell import run_command
from pytest_testconfig import config as py_config

from utilities.constants import REMOTE_KUBECONFIG
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import base64_encode_str, get_hyperconverged_resource

LOGGER = logging.getLogger(__name__)

LIVE_MIGRATION_NETWORK_NAME = "live-migration-network"


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
def remote_admin_client(remote_kubeconfig_export_path):
    """
    Get DynamicClient for a remote cluster
    """
    return get_client(config_file=remote_kubeconfig_export_path)


@pytest.fixture(scope="session")
def remote_cluster_api_url(remote_admin_client):
    """
    Get the API URL of the remote cluster.
    Returns the cluster API endpoint URL (e.g., https://api.cluster-name.example.com:6443)
    """
    api_url = remote_admin_client.configuration.host
    LOGGER.info(f"Remote cluster API URL: {api_url}")
    return api_url


@pytest.fixture(scope="session")
def remote_cluster_auth_token(remote_kubeconfig_export_path):
    """
    Get the authentication token for the remote cluster.

    Returns:
        str: The authentication token for the current user session
    """
    token_command = f"oc whoami -t --kubeconfig={remote_kubeconfig_export_path}"
    token = run_command(command=shlex.split(token_command), verify_stderr=False)[1]

    # Strip any whitespace from the token
    token = token.strip()
    LOGGER.info("Successfully retrieved authentication token for remote cluster")
    return token


@pytest.fixture(scope="session")
def remote_hco_namespace(remote_admin_client):
    return Namespace(client=remote_admin_client, name=py_config["hco_namespace"], ensure_exists=True)


@pytest.fixture(scope="package")
def hyperconverged_resource_scope_package_remote_cluster(remote_admin_client, remote_hco_namespace):
    return get_hyperconverged_resource(client=remote_admin_client, hco_ns_name=remote_hco_namespace.name)


@pytest.fixture(scope="package")
def enabled_feature_gate_for_decentralized_live_migration_remote_cluster(
    hyperconverged_resource_scope_package_remote_cluster,
    remote_admin_client,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_package_remote_cluster: {
                "spec": {"featureGates": {"decentralizedLiveMigration": True}}
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=remote_admin_client,
    ):
        yield


@pytest.fixture(scope="package")
def enabled_feature_gate_for_decentralized_live_migration_local_cluster(
    hyperconverged_resource_scope_package,
    admin_client,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_package: {"spec": {"featureGates": {"decentralizedLiveMigration": True}}}
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=admin_client,
    ):
        yield


@pytest.fixture(scope="package")
def network_for_live_migration_local_cluster(admin_client, hco_namespace):
    return NetworkAttachmentDefinition(
        name=LIVE_MIGRATION_NETWORK_NAME, namespace=hco_namespace.name, client=admin_client, ensure_exists=True
    )


@pytest.fixture(scope="package")
def network_for_live_migration_remote_cluster(remote_admin_client, remote_hco_namespace):
    return NetworkAttachmentDefinition(
        name=LIVE_MIGRATION_NETWORK_NAME,
        namespace=remote_hco_namespace.name,
        client=remote_admin_client,
        ensure_exists=True,
    )


@pytest.fixture(scope="package")
def configured_hco_live_migration_network_local_cluster(
    hyperconverged_resource_scope_package,
    admin_client,
    network_for_live_migration_local_cluster,
):
    """
    Configure the live migration network for HyperConverged resource.
    """
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_package: {
                "spec": {"liveMigrationConfig": {"network": network_for_live_migration_local_cluster.name}}
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=admin_client,
    ):
        yield


@pytest.fixture(scope="package")
def configured_hco_live_migration_network_remote_cluster(
    hyperconverged_resource_scope_package_remote_cluster,
    remote_admin_client,
    network_for_live_migration_remote_cluster,
):
    """
    Configure the live migration network for HyperConverged resource on the remote cluster.
    """
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_package_remote_cluster: {
                "spec": {"liveMigrationConfig": {"network": network_for_live_migration_remote_cluster.name}}
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=remote_admin_client,
    ):
        yield


@pytest.fixture(scope="package")
def mtv_namespace(admin_client):
    return Namespace(name="openshift-mtv", client=admin_client, ensure_exists=True)


@pytest.fixture(scope="package")
def forklift_controller_resource_scope_package(admin_client, mtv_namespace):
    return ForkliftController(
        name="forklift-controller", namespace=mtv_namespace.name, client=admin_client, ensure_exists=True
    )


@pytest.fixture(scope="package")
def enabled_mtv_feature_gate_ocp_live_migration(forklift_controller_resource_scope_package):
    forklift_spec_dict = deepcopy(forklift_controller_resource_scope_package.instance.to_dict()["spec"])
    forklift_spec_dict["feature_ocp_live_migration"] = "true"
    ResourceEditor(patches={forklift_controller_resource_scope_package: forklift_spec_dict}).update()


@pytest.fixture(scope="package")
def remote_cluster_secret(admin_client, mtv_namespace, remote_cluster_auth_token, remote_cluster_api_url):
    """
    Create a Secret for remote cluster access from the local cluster.

    The secret contains:
    - insecureSkipVerify: false (base64 encoded)
    - token: authentication token (base64 encoded)
    - url: cluster API URL (base64 encoded)
    """
    with Secret(
        client=admin_client,
        name="source-cluster-secret",
        namespace=mtv_namespace.name,
        data_dict={
            "insecureSkipVerify": base64_encode_str("false"),
            "token": base64_encode_str(remote_cluster_auth_token),
            "url": base64_encode_str(remote_cluster_api_url),
        },
        type="Opaque",
    ) as secret:
        yield secret


@pytest.fixture(scope="package")
def remote_cluster_provider(admin_client, mtv_namespace, remote_cluster_secret, remote_cluster_api_url):
    """
    Create a Provider resource for the remote cluster in the local cluster.

    Used by MTV to connect to the remote OpenShift cluster for migration operations.
    """
    with Provider(
        client=admin_client,
        name="mtv-source-provider",
        namespace=mtv_namespace.name,
        provider_type=Provider.ProviderType.OPENSHIFT,
        url=remote_cluster_api_url,
        secret_name=remote_cluster_secret.name,
        secret_namespace=remote_cluster_secret.namespace,
    ) as provider:
        yield provider


@pytest.fixture(scope="package")
def local_cluster_provider(admin_client, mtv_namespace):
    """
    Get a Provider resource for the local cluster.
    "host" Provider is created by default by MTV.
    """
    return Provider(client=admin_client, name="host", namespace=mtv_namespace.name, ensure_exists=True)
