import logging

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.api_server import APIServer
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.service import Service
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
)
from tests.install_upgrade_operators.crypto_policy.utils import (
    get_resource_crypto_policy,
    update_apiserver_crypto_policy,
)
from utilities.constants import (
    CDI_KUBEVIRT_HYPERCONVERGED,
    CLUSTER,
    KUBEVIRT_HCO_NAME,
    SSP_KUBEVIRT_HYPERCONVERGED,
    TLS_SECURITY_PROFILE,
)
from utilities.exceptions import MissingResourceException
from utilities.infra import is_jira_open

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
def resource_crypto_policy_settings(request):
    yield get_resource_crypto_policy(
        resource=request.param.get(RESOURCE_TYPE_STR),
        name=request.param.get(RESOURCE_NAME_STR),
        namespace=request.param.get(RESOURCE_NAMESPACE_STR),
        key_name=request.param.get(KEY_NAME_STR),
    )


@pytest.fixture(scope="module")
def api_server(admin_client):
    api_server = APIServer(client=admin_client, name=CLUSTER)
    if api_server.exists:
        return api_server
    raise ResourceNotFoundError(f"{api_server.kind}: {CLUSTER} not found.")


@pytest.fixture()
def skip_apiserver_crypto_policy_reset():
    if is_jira_open(jira_id="RHSTOR-6566"):
        pytest.skip(
            "Test skipped as the bug RHSTOR-6566 prevents worker nodes to be READY after apiserver cryptopolicy reset"
        )


@pytest.fixture()
def updated_api_server_crypto_policy(
    skip_apiserver_crypto_policy_reset,
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
def services_to_check_connectivity(hco_namespace):
    services_list = []
    missing_services = []
    services_name_list = [
        "virt-api",
        "ssp-operator-service",
        "ssp-operator-metrics",
        "virt-template-validator",
        "kubemacpool-service",
        "cdi-api",
        "hostpath-provisioner-operator-service",
    ]
    for service_name in services_name_list:
        service = Service(name=service_name, namespace=hco_namespace.name)
        services_list.append(service) if service.exists else missing_services.append(service_name)

    if missing_services:
        raise MissingResourceException(f"Services: {missing_services}.")

    return services_list
