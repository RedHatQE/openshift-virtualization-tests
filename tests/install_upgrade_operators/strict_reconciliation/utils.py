import logging

from dictdiffer import diff
from kubernetes.dynamic import DynamicClient
from ocp_resources.resource import Resource
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_CA_KEY,
    HCO_CR_CERT_CONFIG_DURATION_KEY,
    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY,
    HCO_CR_CERT_CONFIG_SERVER_KEY,
)
from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CERTC_DEFAULT_12H,
    CERTC_DEFAULT_24H,
    CERTC_DEFAULT_48H,
)
from tests.install_upgrade_operators.utils import (
    get_function_name,
    get_network_addon_config,
)
from utilities.constants import TIMEOUT_3MIN, TIMEOUT_5SEC
from utilities.hco import get_hco_spec
from utilities.infra import get_hyperconverged_resource
from utilities.storage import get_hyperconverged_cdi
from utilities.virt import get_hyperconverged_kubevirt

LOGGER = logging.getLogger(__name__)


def verify_spec(expected_spec, get_spec_func):
    samplers = TimeoutSampler(
        wait_timeout=60,
        sleep=5,
        exceptions_dict={AssertionError: []},
        func=lambda: list(diff(expected_spec, get_spec_func())),
    )
    diff_result = None
    try:
        for diff_result in samplers:
            if not diff_result:
                return True

    except TimeoutExpiredError:
        LOGGER.error(
            f"{get_function_name(function_name=get_spec_func)}: Timed out waiting for CR with expected spec."
            f" spec: '{expected_spec}' diff:'{diff_result}'"
        )
        raise


def verify_specs(
    admin_client,
    hco_namespace,
    hco_spec,
    kubevirt_hyperconverged_spec_scope_function,
    cdi_spec,
    cnao_spec,
):
    verify_spec(
        expected_spec=hco_spec,
        get_spec_func=lambda: get_hco_spec(admin_client=admin_client, hco_namespace=hco_namespace),
    )
    verify_spec(
        expected_spec=kubevirt_hyperconverged_spec_scope_function,
        get_spec_func=lambda: (
            get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)
            .instance.to_dict()
            .get("spec")
        ),
    )
    verify_spec(
        expected_spec=cdi_spec,
        get_spec_func=lambda: get_hyperconverged_cdi(admin_client=admin_client).instance.to_dict().get("spec"),
    )
    verify_spec(
        expected_spec=cnao_spec,
        get_spec_func=lambda: get_network_addon_config(admin_client=admin_client).instance.to_dict().get("spec"),
    )
    # when none of the functions above raise TimeoutExpiredError
    return True


def validate_featuregates_not_in_cdi_cr(admin_client, hco_namespace, feature_gates_under_test):
    """
    Validates that all expected featuregates are present in cdi CR

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace (Namespace): Namespace object
        feature_gates_under_test (list): list of featuregates to compare against current list of featuregates
    returns:
        bool: returns True or False
    """
    cdi = get_hyperconverged_cdi(admin_client=admin_client).instance.to_dict()

    cdi_fgs = cdi["spec"]["config"]["featureGates"]
    return all(fg not in cdi_fgs for fg in feature_gates_under_test)


def compare_expected_with_cr(expected, actual):
    # filtering out the "add" verb - it contains additional keys that do not exist in the expected dict, and are
    # other fields in the spec that are not tested and irrelevant to this test
    return list(
        filter(
            lambda diff_result_item: diff_result_item[0] != "add",
            list(diff(expected, actual)),
        )
    )


def expected_certconfig_stanza():
    return {
        HCO_CR_CERT_CONFIG_CA_KEY: {
            HCO_CR_CERT_CONFIG_DURATION_KEY: CERTC_DEFAULT_48H,
            HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: CERTC_DEFAULT_24H,
        },
        HCO_CR_CERT_CONFIG_SERVER_KEY: {
            HCO_CR_CERT_CONFIG_DURATION_KEY: CERTC_DEFAULT_24H,
            HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: CERTC_DEFAULT_12H,
        },
    }


def wait_for_fg_update(admin_client, hco_namespace, expected_fg, validate_func):
    """
    Waits for featuregate updates to get propagated

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace (Namespace): Namespace object
        expected_fg (list): list of featuregates to compare against current list of featuregates
        validate_func (function): validate function to be used for comparison
    """
    samples = TimeoutSampler(
        wait_timeout=30,
        sleep=1,
        func=validate_func,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        feature_gates_under_test=expected_fg,
    )
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Timeout validating featureGates field values using "
            f"{get_function_name(function_name=validate_func)}: comparing with fg: {expected_fg}"
        )
        raise


def get_hco_related_object_version(client, hco_namespace, resource_name, resource_kind):
    """
    Gets related object version from hco.status.relatedObject

    Args:
        client (DynamicClient): Dynamic client object
        hco_namespace (Namespace): Namespace object
        resource_name (str): Name of the resource
        resource_kind (str): resource kind

    Returns:
        str: current resourceVersion from hco.status.relatedObject
    """
    related_objects = get_hyperconverged_resource(
        client=client, hco_ns_name=hco_namespace.name
    ).instance.status.relatedObjects
    for related_obj in related_objects:
        if related_obj["kind"] == resource_kind and related_obj["name"] == resource_name:
            return related_obj["resourceVersion"]


def wait_for_hco_related_object_version_change(admin_client, hco_namespace, resource, resource_kind):
    """
    Waits for hco.status.relatedObject to get updated with expected resourceVersion value

    Args:
        admin_client (DynamicClient): Dynamic client object
        hco_namespace (Namespace): Namespace object
        resource (Resource): Resource object
        resource_kind (str): resource kind
    """
    resource_name = resource.name
    expected_version = resource.instance.metadata.resourceVersion
    LOGGER.info(f"waiting for {resource_name}/{resource_kind} to reach {expected_version}")
    samplers = TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=TIMEOUT_5SEC,
        func=get_hco_related_object_version,
        client=admin_client,
        hco_namespace=hco_namespace,
        resource_kind=resource_kind,
        resource_name=resource_name,
    )
    resource_version = None
    try:
        for resource_version in samplers:
            if resource_version >= expected_version:
                LOGGER.info(
                    f"For {resource_name}, current resource version {resource_version} >= {expected_version}"
                    f" value in hco.status.relatedObjects."
                )
                return

    except TimeoutExpiredError:
        LOGGER.error(
            f"Component: {resource_name}/{resource_kind} hco.status.relatedObjects was not updated with correct "
            f"resource version: {expected_version}. Actual value: {resource_version}"
        )
        raise


def validate_related_objects(admin_client, hco_namespace, resource, pre_update_resource_version):
    """
    Validates appropriate resourceVersion gets reported after a given related object gets reconciled

    Args:
        admin_client (DynamicClient): Dynamic client object
        hco_namespace (Namespace): Namespace object
        resource (Resource): Resource object
        pre_update_resource_version (str): The resource version pre-update
    """
    wait_for_resource_version_update(
        resource=resource,
        pre_update_resource_version=pre_update_resource_version,
    )
    wait_for_hco_related_object_version_change(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        resource=resource,
        resource_kind=resource.kind,
    )


def wait_for_resource_version_update(resource, pre_update_resource_version):
    """
    Validates a resource is getting reconciled post patch command

    Args:
        resource (Resource): Resource object to be checked
        pre_update_resource_version (str): string indicating pre patch resource version

    Raises:
        TimeoutExpiredError: if related objects are not reconciled, if resourceVersion is not updated for HCO
    """
    samplers = TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: resource.instance.metadata.resourceVersion != pre_update_resource_version,
    )
    try:
        for sample in samplers:
            if sample:
                LOGGER.info(
                    f"For {resource.name} resourceVersion changed from {pre_update_resource_version} "
                    f"to {resource.instance.metadata.resourceVersion}"
                )
                return
    except TimeoutExpiredError:
        LOGGER.error(f"For {resource.name} resourceVersion did not change from {pre_update_resource_version}")
        raise


def get_resource_object(
    resource: type[Resource], resource_name: str, resource_namespace: str, admin_client: DynamicClient
) -> Resource:
    if "NamespacedResource" in str(resource.__base__):
        resource = resource(name=resource_name, namespace=resource_namespace, client=admin_client)
    else:
        resource = resource(name=resource_name, client=admin_client)
    assert resource.exists, f"Resource: {resource_name} not found."
    return resource


def get_resource_version_from_related_object(hco_related_objects, resource):
    for related_object in hco_related_objects:
        if related_object["kind"] == resource.kind:
            return related_object["resourceVersion"]
