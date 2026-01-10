import logging
import os
import re
import tempfile
from copy import deepcopy

import pytest
import requests

from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.data_source import DataSource
from ocp_resources.forklift_controller import ForkliftController
from ocp_resources.migration import Migration
from ocp_resources.namespace import Namespace
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition
from ocp_resources.network_map import NetworkMap
from ocp_resources.plan import Plan
from ocp_resources.provider import Provider
from ocp_resources.resource import ResourceEditor, get_client
from ocp_resources.route import Route
from ocp_resources.secret import Secret
from ocp_resources.storage_map import StorageMap
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from pytest_testconfig import config as py_config

from tests.storage.cross_cluster_live_migration.utils import (
    enable_feature_gate_and_configure_hco_live_migration_network,
    get_vm_boot_time_via_console,
)
from utilities.constants import (
    OS_FLAVOR_RHEL,
    RHEL10_PREFERENCE,
    RHEL10_STR,
    TIMEOUT_1MIN,
    TIMEOUT_30SEC,
    U1_SMALL,
    Images,
)
from utilities.infra import create_ns, get_hyperconverged_resource
from utilities.storage import data_volume_template_with_source_ref_dict, write_file
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)

LIVE_MIGRATION_NETWORK_NAME = "lm-network"


@pytest.fixture(scope="session")
def remote_cluster_credentials(request):
    """
    Get remote cluster credentials from CLI arguments.
    """
    host = request.session.config.getoption("--remote_cluster_host")
    username = request.session.config.getoption("--remote_cluster_username")
    password = request.session.config.getoption("--remote_cluster_password")

    if not all([host, username, password]):
        raise ValueError(
            "Remote cluster credentials not provided. "
            "Use --remote_cluster_host, --remote_cluster_username, and --remote_cluster_password CLI arguments"
        )

    return {
        "host": host,
        "username": username,
        "password": password,
    }


@pytest.fixture(scope="session")
def remote_admin_client(request, remote_cluster_credentials):
    """
    Get DynamicClient for a remote cluster using username/password authentication.
    """
    return get_client(
        username=remote_cluster_credentials["username"],
        password=remote_cluster_credentials["password"],
        host=remote_cluster_credentials["host"],
        verify_ssl=False,
    )


@pytest.fixture(scope="session")
def remote_cluster_api_url(remote_cluster_credentials):
    """
    Returns the cluster API endpoint URL (e.g., https://api.cluster-name.example.com:6443)
    """
    return remote_cluster_credentials["host"]


@pytest.fixture(scope="session")
def remote_cluster_auth_token(remote_admin_client):
    """
    Extract the authentication token from the remote admin client.
    The kubernetes client stores the bearer token in configuration.api_key['authorization'].
    """
    if token_match := re.match(r"Bearer (.*)", remote_admin_client.configuration.api_key.get("authorization", "")):
        return token_match.group(1)
    raise NotFoundError("Unable to extract authentication token from remote admin client")


@pytest.fixture(scope="session")
def remote_cluster_kubeconfig(remote_admin_client, remote_cluster_auth_token):
    """
    Generate a kubeconfig file from the remote admin client credentials.
    Returns the path to the generated kubeconfig file.
    """
    # Extract cluster information from the client
    cluster_host = remote_admin_client.configuration.host
    cluster_name = "remote-cluster"
    user_name = "remote-admin"
    context_name = "remote-context"

    # Create kubeconfig structure
    kubeconfig_dict = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": cluster_name,
                "cluster": {
                    "server": cluster_host,
                    "insecure-skip-tls-verify": True,  # Since we're using verify_ssl=False
                },
            }
        ],
        "users": [{"name": user_name, "user": {"token": remote_cluster_auth_token}}],
        "contexts": [{"name": context_name, "context": {"cluster": cluster_name, "user": user_name}}],
        "current-context": context_name,
    }

    # Create temporary file for kubeconfig
    temp_dir = tempfile.mkdtemp(suffix="-remote-kubeconfig")
    kubeconfig_path = os.path.join(temp_dir, "kubeconfig")

    with open(kubeconfig_path, "w") as f:
        yaml.safe_dump(kubeconfig_dict, f)

    LOGGER.info(f"Created remote cluster kubeconfig at: {kubeconfig_path}")

    yield kubeconfig_path

    # Cleanup
    try:
        os.remove(kubeconfig_path)
        os.rmdir(temp_dir)
        LOGGER.info(f"Cleaned up remote cluster kubeconfig at: {kubeconfig_path}")
    except Exception as e:
        LOGGER.warning(f"Failed to cleanup remote cluster kubeconfig: {e}")


@pytest.fixture(scope="session")
def remote_cluster_hco_namespace(remote_admin_client):
    return Namespace(client=remote_admin_client, name=py_config["hco_namespace"], ensure_exists=True)


@pytest.fixture(scope="package")
def remote_cluster_hyperconverged_resource_scope_package(remote_admin_client, remote_cluster_hco_namespace):
    return get_hyperconverged_resource(client=remote_admin_client, hco_ns_name=remote_cluster_hco_namespace.name)


@pytest.fixture(scope="package")
def local_cluster_enabled_feature_gate_and_configured_hco_live_migration_network(
    hyperconverged_resource_scope_package,
    admin_client,
    local_cluster_network_for_live_migration,
    hco_namespace,
):
    """
    Configure HCO with both decentralized live migration feature gate and live migration network.
    """
    yield from enable_feature_gate_and_configure_hco_live_migration_network(
        hyperconverged_resource=hyperconverged_resource_scope_package,
        client=admin_client,
        network_for_live_migration=local_cluster_network_for_live_migration,
        hco_namespace=hco_namespace,
    )


@pytest.fixture(scope="package")
def local_cluster_network_for_live_migration(admin_client, hco_namespace):
    return NetworkAttachmentDefinition(
        name=LIVE_MIGRATION_NETWORK_NAME,
        namespace=hco_namespace.name,
        client=admin_client,
        ensure_exists=True,
    )


@pytest.fixture(scope="package")
def remote_cluster_network_for_live_migration(remote_admin_client, remote_cluster_hco_namespace):
    return NetworkAttachmentDefinition(
        name=LIVE_MIGRATION_NETWORK_NAME,
        namespace=remote_cluster_hco_namespace.name,
        client=remote_admin_client,
        ensure_exists=True,
    )


@pytest.fixture(scope="package")
def remote_cluster_enabled_feature_gate_and_configured_hco_live_migration_network(
    remote_cluster_hyperconverged_resource_scope_package,
    remote_admin_client,
    remote_cluster_network_for_live_migration,
    remote_cluster_hco_namespace,
):
    """
    Configure the live migration network for HyperConverged resource on the remote cluster.
    """
    yield from enable_feature_gate_and_configure_hco_live_migration_network(
        hyperconverged_resource=remote_cluster_hyperconverged_resource_scope_package,
        client=remote_admin_client,
        network_for_live_migration=remote_cluster_network_for_live_migration,
        hco_namespace=remote_cluster_hco_namespace,
    )


@pytest.fixture(scope="package")
def mtv_namespace(admin_client):
    return Namespace(name="openshift-mtv", client=admin_client, ensure_exists=True)


@pytest.fixture(scope="package")
def forklift_controller_resource_scope_package(admin_client, mtv_namespace):
    return ForkliftController(
        name="forklift-controller", namespace=mtv_namespace.name, client=admin_client, ensure_exists=True
    )


@pytest.fixture(scope="package")
def local_cluster_enabled_mtv_feature_gate_ocp_live_migration(forklift_controller_resource_scope_package):
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
    forklift_services_route_instance = forklift_services_route.instance
    route_host = forklift_services_route_instance.spec.get("host")
    assert route_host, f"forklift-services Route spec.host not found: {forklift_services_route_instance}"
    return route_host


@pytest.fixture(scope="module")
def local_cluster_ca_cert_for_remote_cluster(mtv_forklift_services_route_host, remote_cluster_api_url):
    """
    Fetch the CA certificate for the remote cluster using Forklift services.

    Returns:
        str: The CA certificate content
    """
    cert_url = f"https://{mtv_forklift_services_route_host}/tls-certificate?URL={remote_cluster_api_url}"

    LOGGER.info(f"Fetching remote cluster CA certificate from: {cert_url}")
    response = requests.get(cert_url, verify=False, timeout=TIMEOUT_30SEC)
    response.raise_for_status()

    # The response should contain the certificate
    if ca_cert := response.text.strip():
        LOGGER.info("Successfully fetched remote cluster CA certificate")
        return ca_cert
    raise NotFoundError(f"Empty certificate received from {cert_url}")


@pytest.fixture(scope="module")
def local_cluster_secret_for_remote_cluster(
    admin_client, namespace, remote_cluster_auth_token, remote_cluster_api_url, local_cluster_ca_cert_for_remote_cluster
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
        string_data={
            "insecureSkipVerify": "false",
            "token": remote_cluster_auth_token,
            "url": remote_cluster_api_url,
            "cacert": local_cluster_ca_cert_for_remote_cluster,
        },
        type="Opaque",
    ) as secret:
        yield secret


@pytest.fixture(scope="module")
def local_cluster_mtv_provider_for_remote_cluster(
    admin_client, mtv_namespace, local_cluster_secret_for_remote_cluster, remote_cluster_api_url
):
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
        secret_name=local_cluster_secret_for_remote_cluster.name,
        secret_namespace=local_cluster_secret_for_remote_cluster.namespace,
    ) as provider:
        provider.wait_for_condition(
            condition=provider.Condition.READY, status=provider.Condition.Status.TRUE, timeout=TIMEOUT_30SEC
        )
        yield provider


@pytest.fixture(scope="module")
def local_cluster_mtv_provider_for_local_cluster(admin_client, mtv_namespace):
    """
    Get a Provider resource for the local cluster.
    "host" Provider is created by default by MTV.
    """
    provider = Provider(client=admin_client, name="host", namespace=mtv_namespace.name)
    provider.wait()
    provider.wait_for_condition(
        condition=provider.Condition.READY, status=provider.Condition.Status.TRUE, timeout=TIMEOUT_1MIN
    )
    return provider


@pytest.fixture(scope="module")
def local_cluster_mtv_storage_map(
    admin_client, local_cluster_mtv_provider_for_local_cluster, local_cluster_mtv_provider_for_remote_cluster
):
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
        namespace=local_cluster_mtv_provider_for_local_cluster.namespace,
        source_provider_name=local_cluster_mtv_provider_for_remote_cluster.name,
        source_provider_namespace=local_cluster_mtv_provider_for_remote_cluster.namespace,
        destination_provider_name=local_cluster_mtv_provider_for_local_cluster.name,
        destination_provider_namespace=local_cluster_mtv_provider_for_local_cluster.namespace,
        mapping=mapping,
    ) as storage_map:
        storage_map.wait_for_condition(
            condition=storage_map.Condition.READY, status=storage_map.Condition.Status.TRUE, timeout=TIMEOUT_30SEC
        )
        yield storage_map


@pytest.fixture(scope="module")
def local_cluster_mtv_network_map(
    admin_client, local_cluster_mtv_provider_for_local_cluster, local_cluster_mtv_provider_for_remote_cluster
):
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
        namespace=local_cluster_mtv_provider_for_local_cluster.namespace,
        source_provider_name=local_cluster_mtv_provider_for_remote_cluster.name,
        source_provider_namespace=local_cluster_mtv_provider_for_remote_cluster.namespace,
        destination_provider_name=local_cluster_mtv_provider_for_local_cluster.name,
        destination_provider_namespace=local_cluster_mtv_provider_for_local_cluster.namespace,
        mapping=mapping,
    ) as network_map:
        network_map.wait_for_condition(
            condition=network_map.Condition.READY, status=network_map.Condition.Status.TRUE, timeout=TIMEOUT_30SEC
        )
        yield network_map


@pytest.fixture(scope="session")
def remote_cluster_golden_images_namespace(remote_admin_client):
    return Namespace(name=py_config["golden_images_namespace"], client=remote_admin_client, ensure_exists=True)


@pytest.fixture(scope="class")
def remote_cluster_source_test_namespace(remote_admin_client, unique_suffix):
    yield from create_ns(
        admin_client=remote_admin_client,
        name=f"test-cclm-source-namespace-{unique_suffix}",
    )


@pytest.fixture(scope="class")
def remote_cluster_rhel10_data_source(remote_admin_client, remote_cluster_golden_images_namespace):
    return DataSource(
        namespace=remote_cluster_golden_images_namespace.name,
        name=RHEL10_STR,
        client=remote_admin_client,
        ensure_exists=True,
    )


@pytest.fixture(scope="class")
def vm_for_cclm_from_template_with_data_source(
    remote_admin_client,
    remote_cluster_source_test_namespace,
    remote_cluster_rhel10_data_source,
    remote_cluster_kubeconfig,
):
    with VirtualMachineForTests(
        name="vm-from-template-and-data-source",
        namespace=remote_cluster_source_test_namespace.name,
        client=remote_admin_client,
        os_flavor=OS_FLAVOR_RHEL,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=remote_cluster_rhel10_data_source,
            storage_class=py_config["default_storage_class"],
        ),
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)  # False because we can't ssh to a VM in the remote cluster
        write_file(
            vm=vm,
            filename="test-file",
            content="test-content",
            stop_vm=False,
            kubeconfig=remote_cluster_kubeconfig,
        )
        yield vm


@pytest.fixture(scope="class")
def vms_boot_time_before_cclm(vms_for_cclm, remote_cluster_kubeconfig):
    yield {vm.name: get_vm_boot_time_via_console(vm=vm, kubeconfig=remote_cluster_kubeconfig) for vm in vms_for_cclm}


@pytest.fixture(scope="class")
def vm_for_cclm_with_instance_type(
    remote_admin_client, remote_cluster_source_test_namespace, remote_cluster_rhel10_data_source
):
    with VirtualMachineForTests(
        name="vm-with-instance-type",
        namespace=remote_cluster_source_test_namespace.name,
        client=remote_admin_client,
        os_flavor=OS_FLAVOR_RHEL,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL, client=remote_admin_client),
        vm_preference=VirtualMachineClusterPreference(name=RHEL10_PREFERENCE, client=remote_admin_client),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=remote_cluster_rhel10_data_source,
            storage_class=py_config["default_storage_class"],
        ),
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)  # False because we can't ssh to a VM in the remote cluster
        yield vm


@pytest.fixture(scope="class")
def vms_for_cclm(request):
    """
    Only fixtures from the "vms_fixtures" test param will be called
    Only VMs that are listed in "vms_fixtures" param will be created
    VM fixtures that are not listed in the param will not be called, and those VMs will not be created
    """
    vms = [request.getfixturevalue(argname=vm_fixture) for vm_fixture in request.param["vms_fixtures"]]
    yield vms


@pytest.fixture(scope="class")
def mtv_migration_plan(
    admin_client,
    mtv_namespace,
    local_cluster_mtv_provider_for_local_cluster,
    local_cluster_mtv_provider_for_remote_cluster,
    local_cluster_mtv_storage_map,
    local_cluster_mtv_network_map,
    namespace,
    vms_for_cclm,
    unique_suffix,
):
    """
    Create a Plan resource for MTV cross-cluster live migration.
    This plan configures a live migration from the remote cluster to the local cluster.
    """
    vms = [
        {
            "id": vm.instance.metadata.uid,
            "name": vm.name,
            "namespace": vm.namespace,
        }
        for vm in vms_for_cclm
    ]
    with Plan(
        client=admin_client,
        name=f"cclm-migration-plan-{unique_suffix}",
        namespace=mtv_namespace.name,
        network_map_name=local_cluster_mtv_network_map.name,
        network_map_namespace=local_cluster_mtv_network_map.namespace,
        storage_map_name=local_cluster_mtv_storage_map.name,
        storage_map_namespace=local_cluster_mtv_storage_map.namespace,
        source_provider_name=local_cluster_mtv_provider_for_remote_cluster.name,
        source_provider_namespace=local_cluster_mtv_provider_for_remote_cluster.namespace,
        destination_provider_name=local_cluster_mtv_provider_for_local_cluster.name,
        destination_provider_namespace=local_cluster_mtv_provider_for_local_cluster.namespace,
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
):
    """
    Create a Migration resource to execute the MTV migration plan.
    This triggers the actual migration process for all VMs in the plan.
    """
    with Migration(
        client=admin_client,
        name=f"migration-{mtv_migration_plan.name}",
        namespace=mtv_namespace.name,
        plan_name=mtv_migration_plan.name,
        plan_namespace=mtv_migration_plan.namespace,
    ) as migration:
        yield migration
