import logging
from contextlib import contextmanager

import deepdiff
from benedict import benedict
from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.resource import Resource, ResourceEditor
from packaging.version import Version
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.constants import (
    KEY_NAME_STR,
    RESOURCE_NAME_STR,
    RESOURCE_NAMESPACE_STR,
)
from tests.install_upgrade_operators.crypto_policy.constants import (
    CRYPTO_POLICY_EXPECTED_DICT,
    MANAGED_CRS_LIST,
    MIN_TLS_VERSIONS,
    TLS_INTERMEDIATE_CIPHERS_IANA_OPENSSL_SYNTAX,
)
from tests.install_upgrade_operators.utils import (
    get_resource_key_value,
)
from tests.utils import get_resource_by_name
from utilities.constants import (
    CLUSTER,
    TIMEOUT_2MIN,
    TLS_SECURITY_PROFILE,
)
from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_hco_conditions
from utilities.infra import ExecCommandOnPod
from utilities.operator import wait_for_cluster_operator_stabilize

LOGGER = logging.getLogger(__name__)


def get_resource_crypto_policy(
    resource: Resource, name: str, key_name: str, admin_client: DynamicClient, namespace: str | None = None
) -> dict | None:
    """
    This function is used to get crypto policy settings associated with a resource

    Args:
        resource (Resource): Resource kind
        name (str): name of a resource
        key_name (str): full key path with separator
        namespace (str, optional): namespace for the resource
        admin_client (DynamicClient): Dynamic client object

    Returns:
        dict | None: crypto policy settings value associated with the resource
    """
    return get_resource_key_value(
        key_name=key_name,
        resource=get_resource_by_name(
            resource_kind=resource, name=name, admin_client=admin_client, namespace=namespace
        ),
    )


def get_resources_crypto_policy_dict(
    resources_dict: dict, admin_client: DynamicClient, resources: list[Resource] = MANAGED_CRS_LIST
) -> dict:
    """
    This function collects crypto policy corresponding to each resources in the list
    'resources'

    Args:
        resources_dict (dict): Dict containing resource name, key_name, namespace
        resources (list): List of resource objects whose TLS policies are required
        admin_client (DynamicClient): Dynamic client object

    Returns:
        dict: crypto policy settings value for each resource in 'resources'
    """
    return {
        resource: get_resource_crypto_policy(
            resource=resource,
            name=resources_dict[resource][RESOURCE_NAME_STR],
            key_name=resources_dict[resource][KEY_NAME_STR],
            admin_client=admin_client,
            namespace=resources_dict[resource].get(RESOURCE_NAMESPACE_STR),
        )
        for resource in resources
    }


def wait_for_crypto_policy_update(
    resource: Resource,
    resource_namespace: str,
    resource_name: str,
    key_name: str,
    expected_policy: dict,
    admin_client: DynamicClient,
) -> str | None:
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=2,
        func=get_resource_crypto_policy,
        resource=resource,
        name=resource_name,
        key_name=key_name,
        admin_client=admin_client,
        namespace=resource_namespace,
    )
    sample = None
    try:
        for sample in sampler:
            # TODO: remove log message once the test and feature deemed to be stable
            LOGGER.info(f"{resource_name} actual: {sample}, expected: {expected_policy}")
            if sample and not deepdiff.DeepDiff(
                sample,
                expected_policy,
                ignore_type_in_groups=[(benedict, dict)],
            ):
                return None
    except TimeoutExpiredError:
        error_message = (
            f"For resource {resource} {resource_name}, expected policy {expected_policy}, did not match {sample} "
        )
        LOGGER.error(error_message)
        return error_message
    return None


def assert_crypto_policy_propagated_to_components(
    crypto_policy: str,
    resources_dict: dict,
    updated_resource_kind: str,
    admin_client: DynamicClient,
) -> None:
    """
    This function is used to assert whether the updated crypto policy settings
    propagated to all CNV components - CDI, KubeVirt, CNAO & SSP

    Args:
        crypto_policy (str): Name of the policy ( "old" or "custom" )
        resources_dict (dict): values for resources(name,key_name,namespace_name)
                               in dict
        updated_resource_kind (str): Resource kind of the updated resource
            ( HyperConverged or APIServer )
        admin_client (DynamicClient): Dynamic client object

    Raises:
        AssertionError: When TLS crypto policy of HCO managed CRs(KubeVirt, SSP, CNAO
        & CDI) doesn't match with the expected 'crypto_policy'
    """
    conflicting_resources = []
    for resource in MANAGED_CRS_LIST:
        expected_value = CRYPTO_POLICY_EXPECTED_DICT[crypto_policy][resource]
        error_message = wait_for_crypto_policy_update(
            resource=resource,
            resource_namespace=resources_dict[resource].get(RESOURCE_NAMESPACE_STR),
            resource_name=resources_dict[resource][RESOURCE_NAME_STR],
            key_name=resources_dict[resource][KEY_NAME_STR],
            expected_policy=expected_value,
            admin_client=admin_client,
        )
        if error_message:
            conflicting_resources.append(resource.kind)
    assert not conflicting_resources, (
        f"After updating the resource {updated_resource_kind} with {crypto_policy}, "
        f"following CRs are found inconsistent: {','.join(conflicting_resources)}"
    )


def assert_no_crypto_policy_in_hco(
    crypto_policy: str, hco_namespace: str, hco_name: str, admin_client: DynamicClient
) -> None:
    hco_crypto_policy = get_resource_crypto_policy(
        resource=HyperConverged,
        name=hco_name,
        key_name=TLS_SECURITY_PROFILE,
        admin_client=admin_client,
        namespace=hco_namespace,
    )
    assert not hco_crypto_policy, (
        f"On updating APIServer {CLUSTER} with {crypto_policy}, HCO crypto policy was set up to {hco_crypto_policy}:"
    )


def compose_openssl_command(service_spec, version, cipher="", extra_arguments=""):
    return (
        f"openssl s_client -connect {service_spec.clusterIP}:{service_spec.ports[0].port} "
        f"-tls{version.replace('.', '_')} {cipher} -brief <<< 'Q' 2>&1 {extra_arguments}"
    )


def assert_tls_version_connection(utility_pods, node, services, minimal_version, fips_enabled):
    failed_service = {}
    skip_tls_version = "1.2"
    for service in services:
        service_instance = service.instance
        service_name = service_instance.metadata.name
        LOGGER.info(f"Checking service: {service_name}")
        for version in set(MIN_TLS_VERSIONS.values()):
            if version == skip_tls_version and fips_enabled:
                LOGGER.info(f"Skipping connection validation for TLSv{skip_tls_version} as it is not supported")
                continue
            cmd = compose_openssl_command(
                service_spec=service_instance.spec,
                version=version,
                extra_arguments="| grep 'Protocol version:'",
            )
            out = ExecCommandOnPod(utility_pods=utility_pods, node=node).exec(command=cmd, ignore_rc=True)
            # All TLS versions below the `minimal` configured version should be blocked
            if Version(version) < Version(minimal_version) and version in out:
                failed_service[service_name] = f"TLS v{version} should be blocked. Expected minimal v{minimal_version}"

            # All versions equal or greater to `minimal` configured should be accepted (present in output)
            if Version(version) >= Version(minimal_version) and version not in out:
                failed_service[service_name] = f"Can't connect with TLS v{version}. Expected minimal v{minimal_version}"

    assert not failed_service, f"Some services connections failed:\n {failed_service}"


def assert_tls_ciphers_blocked(utility_pods, node, services, tls_version, allowed_ciphers):
    failed_service = {}
    for service in services:
        service_name = service.instance.metadata.name
        service_spec = service.instance.spec
        LOGGER.info(f"Checking service: {service_name}")
        for cipher_openssl in TLS_INTERMEDIATE_CIPHERS_IANA_OPENSSL_SYNTAX.values():
            # check only non-allowed ciphers, because not all explicitly set ciphers may be accepted by cluster itself
            if cipher_openssl not in allowed_ciphers:
                cmd = compose_openssl_command(
                    service_spec=service_spec,
                    version=tls_version,
                    cipher=f"-cipher {cipher_openssl}",
                    extra_arguments="| grep 'Ciphersuite:'",
                )
                out = ExecCommandOnPod(utility_pods=utility_pods, node=node).exec(command=cmd, ignore_rc=True)
                if cipher_openssl in out:
                    failed_service[service_name] = (
                        f"Cipher {cipher_openssl} should be blocked. Allowed ciphers: {allowed_ciphers}"
                    )

    assert not failed_service, f"Some services connections failed:\n {failed_service}"


@contextmanager
def set_hco_crypto_policy(hco_resource, tls_spec):
    with ResourceEditorValidateHCOReconcile(
        patches={hco_resource: {"spec": {TLS_SECURITY_PROFILE: tls_spec}}},
        wait_for_reconcile_post_update=True,
        list_resource_reconcile=MANAGED_CRS_LIST,
    ):
        yield


@contextmanager
def update_apiserver_crypto_policy(
    admin_client,
    hco_namespace,
    apiserver,
    tls_spec,
):
    with ResourceEditor(
        patches={apiserver: {"spec": {TLS_SECURITY_PROFILE: tls_spec}}},
    ):
        yield
    wait_for_cluster_operator_stabilize(admin_client=admin_client)
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        list_dependent_crs_to_check=MANAGED_CRS_LIST,
    )
