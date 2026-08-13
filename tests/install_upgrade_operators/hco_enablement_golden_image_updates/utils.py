import logging
import re
from typing import Any

from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.image_stream import ImageStream
from ocp_resources.resource import Resource

from tests.install_upgrade_operators.constants import CUSTOM_DATASOURCE_NAME
from utilities.constants.hco import SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
from utilities.constants.storage import (
    OUTDATED,
    WILDCARD_CRON_EXPRESSION,
)
from utilities.constants.timeouts import TIMEOUT_10MIN

HCO_CR_DATA_IMPORT_SCHEDULE_KEY = "dataImportSchedule"
RE_NAMED_GROUP_MINUTES = "minutes"
RE_NAMED_GROUP_HOURS = "hours"
DATA_IMPORT_SCHEDULE_RANDOM_MINUTES_REGEX = (
    rf"(?P<{RE_NAMED_GROUP_MINUTES}>\d+)\s+" rf"(?P<{RE_NAMED_GROUP_HOURS}>\d+)\/12\s+\*\s+\*\s+\*\s*$"
)
COMMON_TEMPLATE = "commonTemplate"
CUSTOM_TEMPLATE = "customTemplate"
CUSTOM_CRON_TEMPLATE = {
    "metadata": {
        "annotations": {
            "cdi.kubevirt.io/storage.bind.immediate.requested": "false",
        },
        "name": "custom-test-cron",
    },
    "spec": {
        "garbageCollect": OUTDATED,
        "importsToKeep": 1,
        "managedDataSource": CUSTOM_DATASOURCE_NAME,
        "retentionPolicy": "None",
        "schedule": WILDCARD_CRON_EXPRESSION,
        "template": {
            "metadata": {},
            "spec": {
                "source": {
                    "registry": {
                        "imageStream": "custom-test-guest",
                        "pullMethod": "node",
                    },
                },
                "storage": {
                    "resources": {
                        "requests": {
                            "storage": "7Gi",
                        }
                    }
                },
            },
        },
    },
}
LOGGER = logging.getLogger(__name__)


def get_random_minutes_hours_fields_from_data_import_schedule(target_string):
    """
    Gets the minutes field from the dataImportSchedule field in HCO CR

    Args:
        target_string (str): dataImportSchedule string (crontab format)

    Raises:
        AssertionError: raised if the regex pattern did not find a match
    """
    re_result = re.match(DATA_IMPORT_SCHEDULE_RANDOM_MINUTES_REGEX, target_string)
    assert re_result, (
        "No regex match against the string: "
        f"regex={DATA_IMPORT_SCHEDULE_RANDOM_MINUTES_REGEX} target_value={target_string}"
    )
    return re_result.group(RE_NAMED_GROUP_MINUTES), re_result.group(RE_NAMED_GROUP_HOURS)


def get_modified_common_template_names(hyperconverged):
    return [
        template["metadata"]["name"]
        for template in get_templates_by_type_from_hco_status(
            hco_status_templates=hyperconverged.instance.to_dict()["status"][SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME],
        )
        if template["status"].get("modified")
    ]


def get_templates_by_type_from_hco_status(hco_status_templates, template_type=COMMON_TEMPLATE):
    return [
        template
        for template in hco_status_templates
        if (template_type == COMMON_TEMPLATE and template["status"].get(template_type))
        or (template_type == CUSTOM_TEMPLATE and not template["status"].get(COMMON_TEMPLATE))
    ]


def get_data_import_crons_by_prefix(
    namespace: str,
    cron_prefix: str,
    admin_client: DynamicClient,
) -> list[DataImportCron]:
    """Return all DataImportCrons matching a template base name prefix.

    Matches exact name or name with architecture suffix (e.g. prefix "fedora"
    matches "fedora", "fedora-amd64", "fedora-arm64").

    Args:
        namespace: Namespace to search in.
        cron_prefix: HCO template base name to match against.
        admin_client: Kubernetes client.

    Returns:
        List of matching DataImportCron resources.

    Raises:
        ResourceNotFoundError: If no matching DataImportCrons are found.
    """
    matching = [
        data_import_cron
        for data_import_cron in DataImportCron.get(client=admin_client, namespace=namespace)
        if data_import_cron.name == cron_prefix or data_import_cron.name.startswith(f"{cron_prefix}-")
    ]
    if not matching:
        raise ResourceNotFoundError(f"No DataImportCron with prefix '{cron_prefix}' found in namespace: {namespace}")
    return matching


def verify_common_template_namespace_updated(common_templates: list[dict[str, Any]], namespace_name: str) -> None:
    """Assert that all templates have the expected namespace in their metadata.

    Args:
        common_templates: List of common templates from HCO status.
        namespace_name: Expected namespace name.

    Raises:
        AssertionError: If any template has a different namespace.
    """
    non_updated_templates = []
    for template in common_templates:
        if template["metadata"].get("namespace") != namespace_name:
            non_updated_templates.append(
                f"{template['metadata']['name']} expected namespace: {namespace_name} "
                f"actual: {template['metadata'].get('namespace')}\n"
            )
    assert not non_updated_templates, non_updated_templates


def get_template_dict_by_name(template_name: str, templates: list[dict[str, Any]]) -> dict[str, Any] | None:
    for template in templates:
        if template["metadata"]["name"] == template_name:
            return template
    return None


def get_templates_resources_names_dict(templates: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Extract resource names from HCO DataImportCronTemplates, grouped by kind.

    Returns:
        dict[str, set[str]]: Mapping of resource kind to set of names.
            Keys: DataImportCron.kind and DataSource.kind are always present;
                  ImageStream.kind is present only when templates contain an image stream.
    """
    resource_dict: dict[str, set[str]] = {}
    for template in templates:
        image_stream_name = template["spec"]["template"]["spec"]["source"]["registry"].get("imageStream")
        if image_stream_name:
            resource_dict.setdefault(ImageStream.kind, set()).add(image_stream_name)
        resource_dict.setdefault(DataImportCron.kind, set()).add(template["metadata"]["name"])
        resource_dict.setdefault(DataSource.kind, set()).add(template["spec"]["managedDataSource"])
    return resource_dict


def verify_resource_not_in_ns(resource_type: type[Resource], namespace: str, client: DynamicClient) -> None:
    """Assert that no resources of the given type exist in the namespace.

    Args:
        resource_type: OCP resource class to query.
        namespace: Namespace to check.
        client: OpenShift client.

    Raises:
        AssertionError: If any resources of the given type exist.
    """
    resources = resource_type.get(client=client, namespace=namespace)
    resources_names = {resource.name for resource in resources}
    assert not resources_names, f"{resource_type.kind} resources shouldn't exist in {namespace}: {resources_names}"


def verify_resource_in_ns(
    expected_resource_names: set[str],
    namespace: str,
    client: DynamicClient,
    resource_type: type[Resource],
    ready_condition: str | None = None,
) -> None:
    """Assert that expected resources exist in the namespace and optionally wait for readiness.

    DataSources use a subset check (expected ⊆ actual) because they retain
    architecture-agnostic pointers alongside arch-specific entries.
    All other resource types use an exact-match check (expected == actual).

    Args:
        expected_resource_names: Set of resource names that must be present.
        namespace: Namespace to check.
        client: OpenShift client.
        resource_type: OCP resource class to query.
        ready_condition: If provided, waits up to 10 minutes for each expected
            resource to reach this condition with status True.

    Raises:
        AssertionError: If any expected resources are missing, or if unexpected
            resources exist (for non-DataSource types).
        TimeoutExpiredError: If a resource does not reach the ready condition in time.
    """
    resources = list(resource_type.get(client=client, namespace=namespace))
    resources_names = {resource.name for resource in resources}
    missing_resources_names = expected_resource_names - resources_names
    assert not missing_resources_names, f"Missing {resource_type.kind} in {namespace}: {missing_resources_names}"

    if resource_type is not DataSource:
        extra_resources_names = resources_names - expected_resource_names
        assert not extra_resources_names, f"Unexpected {resource_type.kind} in {namespace}: {extra_resources_names}"

    if ready_condition:
        LOGGER.info(f"Verify that {expected_resource_names} are in {ready_condition} condition")
        for resource in resources:
            if resource.name in expected_resource_names:
                resource.wait_for_condition(
                    condition=ready_condition,
                    status=resource.Condition.Status.TRUE,
                    timeout=TIMEOUT_10MIN,
                )
