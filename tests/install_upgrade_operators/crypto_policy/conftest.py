import logging

import pytest
from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.api_server import APIServer
from ocp_resources.cdi import CDI
from ocp_resources.deployment import Deployment
from ocp_resources.exceptions import ExecOnPodError
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.network_policy import NetworkPolicy
from ocp_resources.pod import Pod
from ocp_resources.service import Service
from ocp_resources.ssp import SSP

from tests.install_upgrade_operators.constants import (
    KEY_NAME_STR,
    KEY_PATH_SEPARATOR,
    KUBEMACPOOL_SERVICE,
    RESOURCE_NAME_STR,
    RESOURCE_NAMESPACE_STR,
    RESOURCE_TYPE_STR,
)
from tests.install_upgrade_operators.crypto_policy.constants import (
    CONSOLE_PLUGIN_SERVICE_PORT,
    CRYPTO_POLICY_SPEC_DICT,
    KUBEVIRT_TLS_CONFIG_STR,
    MANAGED_CRS_LIST_WITH_AAQ,
    PQC_GROUP_SECP256R1_MLKEM768,
    PQC_GROUP_SECP384R1_MLKEM1024,
    PQC_GROUP_X25519_MLKEM768,
    TLS_MODERN_PROFILE,
    VIRT_TEMPLATE_DEPLOYMENT_NAMES,
)
from tests.install_upgrade_operators.crypto_policy.utils import (
    get_node_available_tls_groups,
    get_resource_crypto_policy,
    get_services_pqc_status,
    update_apiserver_crypto_policy,
)
from utilities.constants import (
    CDI_KUBEVIRT_HYPERCONVERGED,
    CLUSTER,
    KUBEVIRT_HCO_NAME,
    SSP_KUBEVIRT_HYPERCONVERGED,
    TIMEOUT_40MIN,
    TLS_SECURITY_PROFILE,
)
from utilities.exceptions import MissingResourceException
from utilities.hco import enabled_aaq_in_hco, update_hco_annotations, wait_for_hco_conditions
from utilities.infra import ExecCommandOnPod
from utilities.operator import wait_for_cluster_operator_stabilize

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def resources_dict(hco_namespace):
    return {
        KubeVirt: {
            RESOURCE_NAME_STR: KUBEVIRT_HCO_NAME,
            RESOURCE_NAMESPACE_STR: hco_namespace.name,
            KEY_NAME_STR: KUBEVIRT_TLS_CONFIG_STR,
        },
        SSP: {
            RESOURCE_NAME_STR: SSP_KUBEVIRT_HYPERCONVERGED,
            RESOURCE_NAMESPACE_STR: hco_namespace.name,
            KEY_NAME_STR: TLS_SECURITY_PROFILE,
        },
        CDI: {
            RESOURCE_NAME_STR: CDI_KUBEVIRT_HYPERCONVERGED,
            KEY_NAME_STR: f"config{KEY_PATH_SEPARATOR}{TLS_SECURITY_PROFILE}",
        },
        NetworkAddonsConfig: {
            RESOURCE_NAME_STR: CLUSTER,
            KEY_NAME_STR: TLS_SECURITY_PROFILE,
        },
    }


@pytest.fixture()
def resource_crypto_policy_settings(request, admin_client):
    yield get_resource_crypto_policy(
        resource=request.param.get(RESOURCE_TYPE_STR),
        name=request.param.get(RESOURCE_NAME_STR),
        key_name=request.param.get(KEY_NAME_STR),
        admin_client=admin_client,
        namespace=request.param.get(RESOURCE_NAMESPACE_STR),
    )


@pytest.fixture(scope="module")
def api_server(admin_client):
    api_server = APIServer(client=admin_client, name=CLUSTER)
    if api_server.exists:
        return api_server
    raise ResourceNotFoundError(f"{api_server.kind}: {CLUSTER} not found.")


@pytest.fixture()
def updated_api_server_crypto_policy(
    admin_client,
    hco_namespace,
    cnv_crypto_policy_matrix__function__,
    api_server,
):
    tls_security_spec = CRYPTO_POLICY_SPEC_DICT.get(cnv_crypto_policy_matrix__function__)
    assert tls_security_spec, f"{cnv_crypto_policy_matrix__function__} needs to be added to {CRYPTO_POLICY_SPEC_DICT}"
    with update_apiserver_crypto_policy(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        apiserver=api_server,
        tls_spec=tls_security_spec,
    ):
        yield


@pytest.fixture(scope="session")
def services_to_check_connectivity(hco_namespace, admin_client):
    services_list = []
    missing_services = []
    services_name_list = [
        "virt-api",
        "ssp-operator-service",
        "ssp-operator-metrics",
        "virt-template-validator",
        KUBEMACPOOL_SERVICE,
        "cdi-api",
        "hostpath-provisioner-operator-service",
    ]
    for service_name in services_name_list:
        service = Service(name=service_name, namespace=hco_namespace.name, client=admin_client)
        services_list.append(service) if service.exists else missing_services.append(service_name)

    if missing_services:
        raise MissingResourceException(f"Services: {missing_services}.")

    return services_list


@pytest.fixture(scope="package")
def enabled_template_feature_gate(admin_client, hco_namespace, hyperconverged_resource_scope_session):
    """Enables the Template feature gate via HCO annotation and waits for virt-template deployments."""
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_session,
        path="developerConfiguration/featureGates/-",
        value="Template",
    ):
        for deployment_name in VIRT_TEMPLATE_DEPLOYMENT_NAMES:
            deployment = Deployment(
                name=deployment_name,
                namespace=hco_namespace.name,
                client=admin_client,
            )
            deployment.wait_for_replicas()
        yield


@pytest.fixture(scope="package")
def cnv_services_with_template(enabled_template_feature_gate, hco_namespace, admin_client):
    """Discovers all CNV services with a clusterIP, including virt-template services."""
    services_list = [
        service
        for service in Service.get(namespace=hco_namespace.name, client=admin_client)
        if service.instance.spec.clusterIP not in (None, "", "None")
    ]
    assert services_list, f"No services found in {hco_namespace.name}"
    service_names = [svc.name for svc in services_list]
    LOGGER.info(f"Discovered {len(services_list)} services with clusterIP: {service_names}")
    return services_list


@pytest.fixture(scope="package")
def services_tls_runtime(cnv_services_with_template, admin_client, hco_namespace, fips_enabled_cluster):
    """Detects TLS runtime (Go or OpenSSL) for each service's backing pod. Only runs on FIPS clusters."""
    if not fips_enabled_cluster:
        return {}
    runtime_map: dict[str, str] = {}
    for service in cnv_services_with_template:
        service_name = service.name
        label_selector = ",".join(f"{key}={value}" for key, value in service.instance.spec.selector.items())
        pods = list(Pod.get(client=admin_client, namespace=hco_namespace.name, label_selector=label_selector))
        try:
            output = pods[0].execute(command=["sh", "-c", "grep -q libssl /proc/1/maps && echo openssl || echo go"])
            runtime_map[service_name] = output.strip()
        except ExecOnPodError, ApiException:
            LOGGER.warning(f"Failed to detect runtime for {service_name}, defaulting to Go")
            runtime_map[service_name] = "go"
    LOGGER.info(f"TLS runtime detection: {runtime_map}")
    return runtime_map


@pytest.fixture(scope="package")
def enabled_aaq(admin_client, hco_namespace, hyperconverged_resource_scope_session):
    with enabled_aaq_in_hco(
        client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_session,
    ):
        yield


@pytest.fixture()
def modern_tls_profile_applied(admin_client, hco_namespace, api_server, enabled_aaq):
    """Applies Modern TLS profile to apiserver, waits for propagation, and reverts on exit."""
    with update_apiserver_crypto_policy(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        apiserver=api_server,
        tls_spec=TLS_MODERN_PROFILE,
    ):
        wait_for_cluster_operator_stabilize(admin_client=admin_client, wait_timeout=TIMEOUT_40MIN)
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            list_dependent_crs_to_check=MANAGED_CRS_LIST_WITH_AAQ,
        )
        yield


@pytest.fixture(scope="module")
def verified_node_pqc_support(workers_utility_pods, worker_node1, fips_enabled_cluster):
    """Verifies that worker node OpenSSL supports required PQC TLS groups."""
    available_groups = get_node_available_tls_groups(
        utility_pods=workers_utility_pods,
        node=worker_node1,
    )
    # X25519MLKEM768 is non-NIST and blocked by the FIPS crypto module
    required_groups = [PQC_GROUP_SECP256R1_MLKEM768, PQC_GROUP_SECP384R1_MLKEM1024]
    if not fips_enabled_cluster:
        required_groups.append(PQC_GROUP_X25519_MLKEM768)
    missing_groups = [group for group in required_groups if group not in available_groups]
    assert not missing_groups, f"PQC groups not found on node: {missing_groups}. Available: {available_groups}"


@pytest.fixture(scope="package")
def console_plugin_test_network_policy(hco_namespace, admin_client):
    """Temporarily allows ingress to kubevirt-console-plugin pods for TLS testing."""
    with NetworkPolicy(
        name="allow-tls-test-console-plugin",
        namespace=hco_namespace.name,
        client=admin_client,
        pod_selector={"matchLabels": {"app.kubernetes.io/component": "kubevirt-console-plugin"}},
        ingress=[{"ports": [{"protocol": "TCP", "port": CONSOLE_PLUGIN_SERVICE_PORT}]}],
        policy_types=["Ingress"],
    ):
        yield


@pytest.fixture(scope="module")
def pqc_status_by_service(
    verified_node_pqc_support,
    enabled_aaq,
    workers_utility_pods,
    worker_node1,
    cnv_services_with_template,
    console_plugin_test_network_policy,
):
    """PQC acceptance status for each CNV service."""
    results = get_services_pqc_status(
        worker_exec=ExecCommandOnPod(utility_pods=workers_utility_pods, node=worker_node1),
        services=cnv_services_with_template,
        pqc_groups=[PQC_GROUP_X25519_MLKEM768, PQC_GROUP_SECP256R1_MLKEM768, PQC_GROUP_SECP384R1_MLKEM1024],
    )
    accepted, rejected, unreachable = [], [], []
    for name, status in results.items():
        if status is True:
            accepted.append(name)
        elif status is False:
            rejected.append(name)
        else:
            unreachable.append(name)
    LOGGER.info(
        f"PQC probe summary: {len(accepted)} accepted, {len(rejected)} rejected ({rejected}),"
        f" {len(unreachable)} unreachable ({unreachable})"
    )
    return results
