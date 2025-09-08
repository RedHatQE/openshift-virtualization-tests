import logging
import os
from copy import deepcopy

import pytest
import requests
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.forklift_controller import ForkliftController
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition
from ocp_resources.provider import Provider
from ocp_resources.resource import ResourceEditor, get_client
from ocp_resources.route import Route
from ocp_resources.secret import Secret
from ocp_resources.service_account import ServiceAccount
from ocp_resources.storage_map import StorageMap
from pytest_testconfig import config as py_config

from tests.cross_cluster_live_migration.utils import wait_for_service_account_token
from utilities.constants import REMOTE_KUBECONFIG, TIMEOUT_30SEC
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import base64_encode_str, get_hyperconverged_resource

LOGGER = logging.getLogger(__name__)

LIVE_MIGRATION_NETWORK_NAME = "lm-network"


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
def remote_cluster_service_account(remote_admin_client):
    with ServiceAccount(
        client=remote_admin_client,
        name="remote-cluster-service-account",
        namespace="default",
    ) as sa:
        yield sa


@pytest.fixture(scope="session")
def remote_cluster_cluster_role_binding(remote_admin_client, remote_cluster_service_account):
    with ClusterRoleBinding(
        name="remote-cluster-cluster-role-binding",
        cluster_role="cluster-admin",
        client=remote_admin_client,
        subjects=[
            {
                "kind": ServiceAccount.kind,
                "name": remote_cluster_service_account.name,
                "namespace": remote_cluster_service_account.namespace,
            }
        ],
    ) as crb:
        yield crb


@pytest.fixture(scope="session")
def remote_cluster_service_account_token_secret(
    remote_admin_client, remote_cluster_service_account, remote_cluster_cluster_role_binding
):
    """
    Create a secret to hold the service account token.
    The secret depends on the cluster role binding to ensure proper permissions.
    """
    with Secret(
        client=remote_admin_client,
        name="remote-cluster-sa-token-secret",
        namespace=remote_cluster_service_account.namespace,
        annotations={
            "kubernetes.io/service-account.name": remote_cluster_service_account.name,
        },
        type="kubernetes.io/service-account-token",
    ) as secret:
        yield secret


@pytest.fixture(scope="session")
def remote_cluster_auth_token(remote_admin_client, remote_cluster_service_account_token_secret):
    """
    Get the authentication token for the remote cluster.

    Returns:
        str: The authentication token for the current user session
    """
    return wait_for_service_account_token(secret=remote_cluster_service_account_token_secret)


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
    ResourceEditor(patches={forklift_controller_resource_scope_package: {"spec": forklift_spec_dict}}).update()


@pytest.fixture(scope="module")
def mtv_forklift_services_route_host(admin_client, mtv_namespace):
    """
    Get the forklift-services route host.
    """
    forklift_services_route_instance = Route(
        client=admin_client,
        name="forklift-services",
        namespace=mtv_namespace.name,
    ).exists

    route_host = forklift_services_route_instance.spec.host
    assert route_host
    return route_host


@pytest.fixture(scope="module")
def remote_cluster_ca_cert(mtv_forklift_services_route_host, remote_cluster_api_url):
    """
    Fetch the CA certificate for the remote cluster using Forklift services.

    Returns:
        str: The CA certificate content
    """
    cert_url = f"https://{mtv_forklift_services_route_host}/tls-certificate?URL={remote_cluster_api_url}"
    LOGGER.info(f"Fetching remote cluster CA certificate from: {cert_url}")
    try:
        response = requests.get(cert_url, verify=False, timeout=30)
        response.raise_for_status()

        # The response should contain the certificate
        ca_cert = response.text.strip()

        if not ca_cert:
            raise ValueError("Empty certificate received from Forklift services")
        LOGGER.info("Successfully fetched remote cluster CA certificate")
        return ca_cert
    except requests.exceptions.RequestException as e:
        LOGGER.error(f"Failed to fetch CA certificate from {cert_url}: {e}")
        raise
    except Exception as e:
        LOGGER.error(f"Unexpected error fetching CA certificate: {e}")
        raise


@pytest.fixture(scope="module")
def remote_cluster_secret(
    admin_client, namespace, remote_cluster_auth_token, remote_cluster_api_url, remote_cluster_ca_cert
):
    """
    Create a Secret for access to the remote cluster from the local cluster.

    The secret contains:
    - insecureSkipVerify: false (base64 encoded)
    - token: authentication token (base64 encoded)
    - url: cluster API URL (base64 encoded)
    - cacert: CA certificate (base64 encoded)
    """
    with Secret(
        client=admin_client,
        name="source-cluster-secret",
        namespace=namespace.name,
        data_dict={
            "insecureSkipVerify": base64_encode_str("false"),
            "token": remote_cluster_auth_token,
            "url": base64_encode_str(remote_cluster_api_url),
            "cacert": base64_encode_str(remote_cluster_ca_cert),
        },
        type="Opaque",
    ) as secret:
        yield secret


@pytest.fixture(scope="module")
def mtv_provider_remote_cluster(admin_client, mtv_namespace, remote_cluster_secret, remote_cluster_api_url):
    """
    Create a Provider resource for the remote cluster in the local cluster.
    Used by MTV to connect to the remote OpenShift cluster for migration operations.
    """
    with Provider(
        client=admin_client,
        name="mtv-source-provider",
        namespace=mtv_namespace.name,  # TODO Use custom namespace after https://issues.redhat.com/browse/MTV-3293 fixed
        provider_type=Provider.ProviderType.OPENSHIFT,
        url=remote_cluster_api_url,
        secret_name=remote_cluster_secret.name,
        secret_namespace=remote_cluster_secret.namespace,
    ) as provider:
        provider.wait_for_condition(
            condition=provider.Condition.READY, status=provider.Condition.Status.TRUE, timeout=TIMEOUT_30SEC
        )
        yield provider


@pytest.fixture(scope="module")
def mtv_provider_local_cluster(admin_client, mtv_namespace):
    """
    Get a Provider resource for the local cluster.
    "host" Provider is created by default by MTV.
    """
    # TODO Use custom namespace after https://issues.redhat.com/browse/MTV-3293 fixed
    provider = Provider(client=admin_client, name="host", namespace=mtv_namespace.name, ensure_exists=True)
    provider.wait_for_condition(
        condition=provider.Condition.READY, status=provider.Condition.Status.TRUE, timeout=TIMEOUT_30SEC
    )
    return provider


@pytest.fixture(scope="module")
def mtv_storage_map(admin_client, mtv_namespace, mtv_provider_local_cluster, mtv_provider_remote_cluster):
    """
    Create a StorageMap resource for MTV migration.
    Maps storage classes between source and destination clusters.
    """
    # Define the storage mapping
    mapping = [
        {
            "source": {"name": py_config["default_storage_class"]},
            "destination": {
                "storageClass": py_config["default_storage_class"]  # TODO Decide on the destination storage class
            },
        }
    ]
    with StorageMap(
        client=admin_client,
        name="storage-map",
        namespace=mtv_namespace.name,
        source_provider_name=mtv_provider_remote_cluster.name,
        source_provider_namespace=mtv_provider_remote_cluster.namespace,
        destination_provider_name=mtv_provider_local_cluster.name,
        destination_provider_namespace=mtv_provider_local_cluster.namespace,
        mapping=mapping,
    ) as storage_map:
        yield storage_map
