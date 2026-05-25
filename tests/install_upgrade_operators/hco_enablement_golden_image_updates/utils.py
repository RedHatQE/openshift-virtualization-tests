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
from utilities.constants import (
    OUTDATED,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
    TIMEOUT_10MIN,
    WILDCARD_CRON_EXPRESSION,
)

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


def get_modifed_common_template_names(hyperconverged):
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


def get_data_import_cron_by_name(namespace: str, cron_name: str, admin_client: DynamicClient) -> DataImportCron:
    data_import_cron = DataImportCron(name=cron_name, namespace=namespace, client=admin_client)
    if data_import_cron.exists:
        return data_import_cron
    raise ResourceNotFoundError(f"DataImportCron: {data_import_cron} not found in namespace: {namespace}")


def get_template_dict_by_name(template_name, templates):
    for template in templates:
        if template["metadata"]["name"] == template_name:
            return template


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
    """Verify that resources exist in namespace and optionally in ready condition."""
    resources = list(resource_type.get(client=client, namespace=namespace))
    resources_names = {resource.name for resource in resources}
    missing_resources_names = expected_resource_names - resources_names
    assert not missing_resources_names, f"Missing {resource_type.kind} in {namespace}: {missing_resources_names}"

    if ready_condition:
        LOGGER.info(f"Verify that {expected_resource_names} are in {ready_condition} condition")
        for resource in resources:
            if resource.name in expected_resource_names:
                resource.wait_for_condition(
                    condition=ready_condition,
                    status=resource.Condition.Status.TRUE,
                    timeout=TIMEOUT_10MIN,
                )
