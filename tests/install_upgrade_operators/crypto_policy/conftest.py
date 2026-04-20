import logging

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.aaq import AAQ
from ocp_resources.api_server import APIServer
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.network_policy import NetworkPolicy
from ocp_resources.ssp import SSP

from tests.install_upgrade_operators.constants import (
    KEY_NAME_STR,
    KEY_PATH_SEPARATOR,
    RESOURCE_NAME_STR,
    RESOURCE_NAMESPACE_STR,
    RESOURCE_TYPE_STR,
)
from tests.install_upgrade_operators.crypto_policy.constants import (
    CRYPTO_POLICY_SPEC_DICT,
    KUBEVIRT_TLS_CONFIG_STR,
    MANAGED_CRS_LIST,
    OPENSSL_CONNECTION_SUCCESS_INDICATOR,
    PQC_GROUP_X25519_MLKEM768,
    PQC_HANDSHAKE_FAILURE_INDICATOR,
    TLS_MODERN_PROFILE,
    TLS_VERSION_1_2,
)
from tests.install_upgrade_operators.crypto_policy.utils import (
    compose_openssl_pqc_command,
    get_node_available_tls_groups,
    get_resource_crypto_policy,
    get_services_accepting_tls_version,
    update_apiserver_crypto_policy,
)
from utilities.constants import (
    AAQ_KUBEVIRT_HYPERCONVERGED,
    CDI_KUBEVIRT_HYPERCONVERGED,
    CLUSTER,
    KUBEVIRT_HCO_NAME,
    SSP_KUBEVIRT_HYPERCONVERGED,
    TLS_SECURITY_PROFILE,
)
from utilities.hco import enabled_aaq_in_hco, wait_for_hco_conditions
from utilities.infra import ExecCommandOnPod
from utilities.operator import wait_for_cluster_operator_stabilize

LOGGER = logging.getLogger(__name__)

CONSOLE_PLUGIN_SERVICE_NAME = "kubevirt-console-plugin-service"
CONSOLE_PLUGIN_SERVICE_PORT = 9443


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
        AAQ: {
            RESOURCE_NAME_STR: AAQ_KUBEVIRT_HYPERCONVERGED,
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
def worker_node(workers):
    return workers[0]


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
        wait_for_cluster_operator_stabilize(admin_client=admin_client)
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            list_dependent_crs_to_check=[*MANAGED_CRS_LIST, AAQ],
        )
        yield


@pytest.fixture()
def services_still_accepting_tls12_under_modern(
    enabled_aaq, modern_tls_profile_applied, workers_utility_pods, worker_node, services_to_check_connectivity
):
    """Services that still accept TLS 1.2 after Modern profile is applied.

    Returns:
        dict: Services that did not reject TLS 1.2 under Modern profile.
    """
    tls12_status = get_services_accepting_tls_version(
        utility_pods=workers_utility_pods,
        node=worker_node,
        services=services_to_check_connectivity,
        tls_version=TLS_VERSION_1_2,
    )
    return {
        name: "TLS 1.2 should be rejected under Modern profile" for name, accepts in tls12_status.items() if accepts
    }


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
    """Temporarily allows ingress to kubevirt-console-plugin pods for TLS testing.

    The console-plugin has a NetworkPolicy that restricts ingress to only the openshift-console namespace.
    This fixture creates an additional NetworkPolicy to allow our test utility pods to reach it.
    """
    LOGGER.info(f"Creating temporary NetworkPolicy to allow test access to {CONSOLE_PLUGIN_SERVICE_NAME}")
    with NetworkPolicy(
        name="allow-tls-test-console-plugin",
        namespace=hco_namespace.name,
        client=admin_client,
        pod_selector={"matchLabels": {"app.kubernetes.io/component": "kubevirt-console-plugin"}},
        ingress=[{"ports": [{"protocol": "TCP", "port": CONSOLE_PLUGIN_SERVICE_PORT}]}],
        policy_types=["Ingress"],
    ):
        yield


@pytest.fixture(scope="session")
def services_accepting_pqc(
    enabled_aaq, worker_exec, services_to_check_connectivity, console_plugin_test_network_policy
):
    """Probes each CNV service with PQC-only (X25519MLKEM768, no classical fallback).

    Returns:
        dict: Services that accepted the PQC handshake.
    """
    accepted_services = {}
    for service in services_to_check_connectivity:
        service_name = service.instance.metadata.name
        LOGGER.info(f"Probing PQC on service: {service_name}")
        command = compose_openssl_pqc_command(service_spec=service.instance.spec, groups=PQC_GROUP_X25519_MLKEM768)
        output = worker_exec.exec(command=command, ignore_rc=True)
        if OPENSSL_CONNECTION_SUCCESS_INDICATOR not in output and PQC_HANDSHAKE_FAILURE_INDICATOR not in output:
            LOGGER.warning(f"Service {service_name} is unreachable, skipping PQC probe")
            continue
        if PQC_HANDSHAKE_FAILURE_INDICATOR not in output:
            accepted_services[service_name] = output[:200]
    return accepted_services
