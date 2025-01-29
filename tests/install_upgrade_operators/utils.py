import importlib
import inspect
import logging
import re

from benedict import benedict
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ConflictError, ResourceNotFoundError
from ocp_resources.installplan import InstallPlan
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.operator_condition import OperatorCondition
from ocp_resources.resource import Resource
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.constants import KEY_PATH_SEPARATOR
from utilities.constants import (
    HCO_SUBSCRIPTION,
    PRODUCTION_CATALOG_SOURCE,
    TIMEOUT_1MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10SEC,
    TIMEOUT_30MIN,
    TIMEOUT_40MIN,
)
from utilities.infra import get_subscription

LOGGER = logging.getLogger(__name__)


def wait_for_operator_condition(dyn_client, hco_namespace, name, upgradable):
    LOGGER.info(f"Wait for the operator condition. Name:{name} Upgradable:{upgradable}")
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_30MIN,
        sleep=TIMEOUT_10SEC,
        func=OperatorCondition.get,
        dyn_client=dyn_client,
        namespace=hco_namespace,
        name=name,
    )
    try:
        for sample in samples:
            for operator_condition in sample:
                operator_spec_condition = operator_condition.instance.spec.conditions
                if operator_spec_condition:
                    upgradeable_condition = next(
                        (condition for condition in operator_spec_condition if condition.type == "Upgradeable"),
                        None,
                    )
                    if upgradeable_condition is not None and upgradeable_condition.status == str(upgradable):
                        return operator_condition
                else:
                    LOGGER.warning(f"Waiting for hco operator to update spec.conditions of OperatorCondition: {name}")
    except TimeoutExpiredError:
        LOGGER.error(f"timeout waiting for operator version: name={name}, upgradable:{upgradable}")
        raise


def wait_for_install_plan(
    dyn_client: DynamicClient,
    hco_namespace: str,
    hco_target_version: str,
    is_production_source: bool,
) -> InstallPlan:
    install_plan_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_40MIN,
        sleep=TIMEOUT_10SEC,
        func=InstallPlan.get,
        exceptions_dict={
            ConflictError: [],
            ResourceNotFoundError: [],
        },  # Ignore ConflictError during install plan reconciliation
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        hco_target_version=hco_target_version,
    )
    subscription = get_subscription(
        admin_client=dyn_client,
        namespace=hco_namespace,
        subscription_name=HCO_SUBSCRIPTION,
    )
    install_plan_name_in_subscription = None
    try:
        for install_plan_samples in install_plan_sampler:
            # wait for the install plan to be created and updated in the subscription.
            install_plan_name_in_subscription = getattr(subscription.instance.status.installplan, "name", None)
            for ip in install_plan_samples:
                # If we find a not-approved install plan that is associated with production catalogsource, we need
                # to delete it. Deleting the install plan associated with production catalogsource, would cause
                # install plan associated with custom catalog source to generate. Upgrade automation is supposed to
                # upgrade cnv using custom catalogsource, to a specified version. Approving install plan associated
                # with the production catalogsource would also lead to failure as production catalogsource has been
                # disabled at this point.
                if ip.exists:
                    ip_instance = ip.instance
                    if not is_production_source:
                        if (
                            not ip_instance.spec.approved
                            and ip_instance.status
                            and ip_instance.status.bundleLookups[0].get("catalogSourceRef").get("name")
                            == PRODUCTION_CATALOG_SOURCE
                        ):
                            ip.clean_up()
                            continue
                    if (
                        hco_target_version == ip_instance.spec.clusterServiceVersionNames[0]
                        and ip.name == install_plan_name_in_subscription
                    ):
                        return ip
                    LOGGER.info(
                        f"Subscription: {subscription.name}, is associated with install plan:"
                        f" {install_plan_name_in_subscription}"
                    )

    except TimeoutExpiredError:
        LOGGER.error(
            f"timeout waiting for target install plan: version={hco_target_version}, "
            f"subscription install plan: {install_plan_name_in_subscription}"
        )
        raise


def get_network_addon_config(admin_client):
    """
    Gets NetworkAddonsConfig object

    Args:
        admin_client (DynamicClient): a DynamicClient object

    Returns:
        Generator of NetworkAddonsConfig: Generator of NetworkAddonsConfig
    """
    for nao in NetworkAddonsConfig.get(dyn_client=admin_client, name="cluster"):
        return nao


def wait_for_spec_change(expected, get_spec_func, base_path):
    """
    Waits for spec values to get propagated

    Args:
        expected (dict): dictionary of values that would be used to update hco cr
        get_spec_func (function): function to fetch current spec dictionary
        base_path (list): list of associated keys for a given kind
    """

    samplers = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: benedict(get_spec_func()),
    )
    current_value = None
    try:
        for current_spec in samplers:
            current_value = current_spec.get(base_path)
            if current_value and sorted(expected.items()) == sorted(current_value.items()):
                LOGGER.info(
                    f"{get_function_name(function_name=get_spec_func)}: Found expected spec values: '{expected}'"
                )
                return True

    except TimeoutExpiredError:
        LOGGER.error(
            f"{get_function_name(function_name=get_spec_func)}: Timed out waiting for CR with expected spec:"
            f" '{expected}', current value:'{current_value}'"
        )
        raise


def get_function_name(function_name):
    """
    Return the text of the source code for a function

    Args:
        function_name (function object): function object

    Returns:
        str: name of the function
    """
    return inspect.getsource(function_name).split("(")[0].split(" ")[-1]


def get_resource_container_env_image_mismatch(container):
    return [
        env_dict
        for env_dict in container.get("env", [])
        if "image" in env_dict["name"].lower()
        and env_dict.get("value")
        and not re.match(
            rf"NOT_AVAILABLE|{Resource.ApiGroup.IMAGE_REGISTRY}",
            env_dict.get("value"),
        )
    ]


def get_ocp_resource_module_name(related_object_kind, list_submodules):
    """
    From a list of ocp_resources submodule, based on kubernetes 'kind' name pick the right module name

    Args:
        related_object_kind (str): Kubernetes kind name of a resource
        list_submodules (list): list of ocp_resources submodule names

    Returns:
        str: Name of the ocp_resources submodule

    Raises:
        ModuleNotFoundError: if a module associated with related object kind is not found
    """
    for module_name in list_submodules:
        expected_module_name = module_name.replace("_", "")
        if related_object_kind.lower() == expected_module_name:
            return module_name
    raise ModuleNotFoundError(f"{related_object_kind} module not found in ocp_resources")


def get_resource(related_obj, admin_client, module_name):
    """
    Gets CR based on associated HCO.status.relatedObject entry and ocp_reources module name

    Args:
        related_obj (dict): Associated HCO.status.relatedObject dict
        admin_client (DynamicClient): Dynamic client object
        module_name (str): Associated ocp_reources module name to be used

    Returns:
        Resource: Associated cr object

    Raises:
        AssertionError: if a related object kind is not in module name
    """
    kwargs = {"client": admin_client, "name": related_obj["name"]}
    if related_obj["namespace"]:
        kwargs["namespace"] = related_obj["namespace"]

    module = importlib.import_module(f"ocp_resources.{module_name}")
    cls_related_obj = getattr(module, related_obj["kind"], None)
    assert cls_related_obj, f"class {related_obj['kind']} is not in {module_name}"
    LOGGER.debug(f"reading class {related_obj['kind']} from module {module_name}")
    return cls_related_obj(**kwargs)


def get_resource_from_module_name(related_obj, ocp_resources_submodule_list, admin_client):
    """
    Gets resource object based on module name

    Args:
        related_obj (dict): Related object Dictionary
        ocp_resources_submodule_list (list): list of submudule names associated with ocp_resources package
        admin_client (DynamicClient): Dynamic client object

    Returns:
        Resource: Associated cr object
    """
    module_name = get_ocp_resource_module_name(
        related_object_kind=related_obj["kind"],
        list_submodules=ocp_resources_submodule_list,
    )
    return get_resource(
        admin_client=admin_client,
        related_obj=related_obj,
        module_name=module_name,
    )


def get_resource_by_name(resource_kind, name, namespace=None):
    kwargs = {"name": name}
    if namespace:
        kwargs["namespace"] = namespace
    resource = resource_kind(**kwargs)
    if resource.exists:
        return resource
    raise ResourceNotFoundError(f"{resource_kind} {name} not found.")


def get_resource_key_value(resource, key_name):
    return benedict(
        resource.instance.to_dict()["spec"],
        keypath_separator=KEY_PATH_SEPARATOR,
    ).get(key_name)
