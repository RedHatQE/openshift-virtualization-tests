import logging

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.aaq import AAQ
from ocp_resources.api_server import APIServer
from ocp_resources.cdi import CDI
from ocp_resources.deployment import Deployment
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.network_policy import NetworkPolicy
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
    CONSOLE_PLUGIN_SERVICE_NAME,
    CONSOLE_PLUGIN_SERVICE_PORT,
    CRYPTO_POLICY_SPEC_DICT,
    KUBEVIRT_TLS_CONFIG_STR,
    MANAGED_CRS_LIST,
    PQC_GROUP_SECP256R1_MLKEM768,
    PQC_GROUP_SECP384R1_MLKEM1024,
    PQC_GROUP_X25519_MLKEM768,
    TLS_MODERN_PROFILE,
    TLS_VERSION_1_2,
    VIRT_TEMPLATE_DEPLOYMENT_NAMES,
)
from tests.install_upgrade_operators.crypto_policy.utils import (
    get_node_available_tls_groups,
    get_resource_crypto_policy,
    get_services_accepting_tls_version,
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


@pytest.fixture(scope="session")
def worker_node(workers):
    return workers[0]


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="session")
def cnv_services_with_template(enabled_template_feature_gate, hco_namespace, admin_client):
    """Discovers all TLS-capable CNV services, including virt-template services."""
    services_list = [
        service
        for service in Service.get(namespace=hco_namespace.name, client=admin_client)
        if service.instance.spec.clusterIP not in (None, "", "None")
    ]
    assert services_list, f"No services found in {hco_namespace.name}"
    service_names = [svc.instance.metadata.name for svc in services_list]
    LOGGER.info(f"Discovered {len(services_list)} TLS-capable services: {service_names}")
    return services_list


@pytest.fixture(scope="session")
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
            list_dependent_crs_to_check=[*MANAGED_CRS_LIST, AAQ],
        )
        yield


@pytest.fixture()
def tls12_status_under_modern_profile(
    enabled_aaq,
    modern_tls_profile_applied,
    workers_utility_pods,
    worker_node,
    cnv_services_with_template,
    console_plugin_test_network_policy,
):
    """TLS 1.2 acceptance status per service after Modern profile is applied."""
    return get_services_accepting_tls_version(
        utility_pods=workers_utility_pods,
        node=worker_node,
        services=cnv_services_with_template,
        tls_version=TLS_VERSION_1_2,
    )


@pytest.fixture(scope="session")
def node_available_tls_groups(workers_utility_pods, worker_node):
    return get_node_available_tls_groups(
        utility_pods=workers_utility_pods,
        node=worker_node,
    )


@pytest.fixture(scope="session")
def worker_exec(workers_utility_pods, worker_node):
    return ExecCommandOnPod(utility_pods=workers_utility_pods, node=worker_node)


@pytest.fixture(scope="session")
def console_plugin_test_network_policy(hco_namespace, admin_client):
    """Temporarily allows ingress to kubevirt-console-plugin pods for TLS testing."""
    network_policy_name = "allow-tls-test-console-plugin"
    stale_policy = NetworkPolicy(
        name=network_policy_name,
        namespace=hco_namespace.name,
        client=admin_client,
    )
    if stale_policy.exists:
        LOGGER.warning(f"Deleting stale NetworkPolicy {network_policy_name} from previous run")
        stale_policy.delete(wait=True)

    LOGGER.info(f"Creating temporary NetworkPolicy to allow test access to {CONSOLE_PLUGIN_SERVICE_NAME}")
    with NetworkPolicy(
        name=network_policy_name,
        namespace=hco_namespace.name,
        client=admin_client,
        pod_selector={"matchLabels": {"app.kubernetes.io/component": "kubevirt-console-plugin"}},
        ingress=[{"ports": [{"protocol": "TCP", "port": CONSOLE_PLUGIN_SERVICE_PORT}]}],
        policy_types=["Ingress"],
    ):
        yield


@pytest.fixture(scope="session")
def pqc_status_by_service(enabled_aaq, worker_exec, cnv_services_with_template, console_plugin_test_network_policy):
    """PQC acceptance status for each CNV service."""
    results = get_services_pqc_status(
        worker_exec=worker_exec,
        services=cnv_services_with_template,
        pqc_groups=[PQC_GROUP_X25519_MLKEM768, PQC_GROUP_SECP256R1_MLKEM768, PQC_GROUP_SECP384R1_MLKEM1024],
    )
    accepted = [name for name, status in results.items() if status is True]
    rejected = [name for name, status in results.items() if status is False]
    unreachable = [name for name, status in results.items() if status is None]
    LOGGER.info(
        f"PQC probe summary: {len(accepted)} accepted, {len(rejected)} rejected, {len(unreachable)} unreachable"
    )
    if rejected:
        LOGGER.info(f"PQC rejected by: {rejected}")
    if unreachable:
        LOGGER.warning(f"Unreachable services: {unreachable}")
    return results
