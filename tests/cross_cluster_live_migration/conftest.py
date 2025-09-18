import logging
import os
import time
from copy import deepcopy

import pytest
import requests
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.data_source import DataSource
from ocp_resources.forklift_controller import ForkliftController
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.migration import Migration
from ocp_resources.namespace import Namespace
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition
from ocp_resources.network_map import NetworkMap
from ocp_resources.plan import Plan
from ocp_resources.provider import Provider
from ocp_resources.resource import ResourceEditor, get_client
from ocp_resources.route import Route
from ocp_resources.secret import Secret
from ocp_resources.service_account import ServiceAccount
from ocp_resources.storage_map import StorageMap
from pytest_testconfig import config as py_config

from tests.cross_cluster_live_migration.utils import wait_for_service_account_token
from utilities.constants import (
    DATA_SOURCE_STR,
    OS_FLAVOR_RHEL,
    REMOTE_KUBECONFIG,
    TIMEOUT_1MIN,
    TIMEOUT_30SEC,
    Images,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import base64_encode_str, create_ns, get_hyperconverged_resource
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

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
    with ResourceEditor(patches={forklift_controller_resource_scope_package: {"spec": forklift_spec_dict}}):
        yield


@pytest.fixture(scope="module")
def mtv_forklift_services_route_host(admin_client, mtv_namespace):
    """
    Get the forklift-services route host.
    """
    forklift_services_route = Route(
        client=admin_client,
        name="forklift-services",
        namespace=mtv_namespace.name,
        ensure_exists=True,
    )
    route_host = forklift_services_route.instance.spec.host
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
def mtv_provider_remote_cluster(admin_client, mtv_namespace, namespace, remote_cluster_secret, remote_cluster_api_url):
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
    provider = Provider(client=admin_client, name="host", namespace=mtv_namespace.name, ensure_exists=True)
    provider.wait_for_condition(
        condition=provider.Condition.READY, status=provider.Condition.Status.TRUE, timeout=TIMEOUT_30SEC
    )
    return provider


@pytest.fixture(scope="module")
def mtv_storage_map(admin_client, mtv_provider_local_cluster, mtv_provider_remote_cluster):
    """
    Create a StorageMap resource for MTV migration.
    Maps storage classes between source and destination clusters.
    """
    mapping = [
        {
            "source": {"name": py_config["default_storage_class"]},
            "destination": {"storageClass": py_config["default_storage_class"]},
        }
    ]
    with StorageMap(
        client=admin_client,
        name="storage-map",
        namespace=mtv_provider_local_cluster.namespace,
        source_provider_name=mtv_provider_remote_cluster.name,
        source_provider_namespace=mtv_provider_remote_cluster.namespace,
        destination_provider_name=mtv_provider_local_cluster.name,
        destination_provider_namespace=mtv_provider_local_cluster.namespace,
        mapping=mapping,
    ) as storage_map:
        storage_map.wait_for_condition(
            condition=storage_map.Condition.READY, status=storage_map.Condition.Status.TRUE, timeout=TIMEOUT_30SEC
        )
        yield storage_map


@pytest.fixture(scope="module")
def mtv_network_map(admin_client, mtv_provider_local_cluster, mtv_provider_remote_cluster):
    """
    Create a NetworkMap resource for MTV migration.
    Maps networks between source and destination clusters.
    """
    mapping = [
        {
            "source": {"type": "pod"},
            "destination": {"type": "pod"},
        }
    ]
    with NetworkMap(
        client=admin_client,
        name="network-map",
        namespace=mtv_provider_local_cluster.namespace,
        source_provider_name=mtv_provider_remote_cluster.name,
        source_provider_namespace=mtv_provider_remote_cluster.namespace,
        destination_provider_name=mtv_provider_local_cluster.name,
        destination_provider_namespace=mtv_provider_local_cluster.namespace,
        mapping=mapping,
    ) as network_map:
        network_map.wait_for_condition(
            condition=network_map.Condition.READY, status=network_map.Condition.Status.TRUE, timeout=TIMEOUT_30SEC
        )
        yield network_map


@pytest.fixture(scope="session")
def remote_golden_images_namespace(remote_admin_client):
    return Namespace(name=py_config["golden_images_namespace"], client=remote_admin_client, ensure_exists=True)


@pytest.fixture(scope="class")
def unique_suffix():
    """
    Returns last 5 digits of timestamp in string format
    """
    return str(int(time.time()))[-5:]


@pytest.fixture(scope="class")
def remote_test_namespace(request, remote_admin_client, unique_suffix):
    yield from create_ns(
        admin_client=remote_admin_client,
        name=f"test-cclm-remote-namespace-{unique_suffix}",
        teardown=True,
    )


@pytest.fixture(scope="class")
def vm_for_cclm_from_template_with_data_source(
    remote_admin_client, remote_test_namespace, remote_golden_images_namespace
):
    rhel_data_source = DataSource(
        namespace=remote_golden_images_namespace.name,
        name=py_config["latest_rhel_os_dict"][DATA_SOURCE_STR],
        client=remote_admin_client,
        ensure_exists=True,
    )
    with VirtualMachineForTests(
        name="vm-from-template-and-data-source",
        namespace=remote_test_namespace.name,
        client=remote_admin_client,
        os_flavor=OS_FLAVOR_RHEL,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel_data_source,
            storage_class=py_config["default_storage_class"],
        ),
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)  # False because we can't ssh to a VM in the remote cluster
        yield vm


@pytest.fixture(scope="class")
def mtv_migration_plan(
    admin_client,
    mtv_namespace,
    mtv_provider_local_cluster,
    mtv_provider_remote_cluster,
    mtv_storage_map,
    mtv_network_map,
    namespace,
    vm_for_cclm_from_template_with_data_source,
    unique_suffix,
):
    """
    Create a Plan resource for MTV cross-cluster live migration.
    This plan configures a live migration from the remote cluster to the local cluster.
    """
    vms = [
        {
            "id": vm_for_cclm_from_template_with_data_source.instance.metadata.uid,
            "name": vm_for_cclm_from_template_with_data_source.name,
            "namespace": vm_for_cclm_from_template_with_data_source.namespace,
        }
    ]
    with Plan(
        client=admin_client,
        name=f"cclm-migration-plan-{unique_suffix}",
        namespace=mtv_namespace.name,
        network_map_name=mtv_network_map.name,
        network_map_namespace=mtv_network_map.namespace,
        storage_map_name=mtv_storage_map.name,
        storage_map_namespace=mtv_storage_map.namespace,
        source_provider_name=mtv_provider_remote_cluster.name,
        source_provider_namespace=mtv_provider_remote_cluster.namespace,
        destination_provider_name=mtv_provider_local_cluster.name,
        destination_provider_namespace=mtv_provider_local_cluster.namespace,
        target_namespace=namespace.name,
        virtual_machines_list=vms,
        type="live",
        warm_migration=False,
        target_power_state="auto",
    ) as plan:
        plan.wait_for_condition(condition=plan.Condition.READY, status=plan.Condition.Status.TRUE, timeout=TIMEOUT_1MIN)
        yield plan


@pytest.fixture(scope="class")
def mtv_migration(
    admin_client,
    mtv_namespace,
    mtv_migration_plan,
    unique_suffix,
):
    """
    Create a Migration resource to execute the MTV migration plan.
    This triggers the actual migration process for all VMs in the plan.
    """
    with Migration(
        client=admin_client,
        name=f"{mtv_migration_plan.name}-{unique_suffix}",
        namespace=mtv_namespace.name,
        plan_name=mtv_migration_plan.name,
        plan_namespace=mtv_migration_plan.namespace,
    ) as migration:
        yield migration
