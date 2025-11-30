import logging
import re
from typing import Any

from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.image_stream import ImageStream
from ocp_resources.resource import Resource

from tests.install_upgrade_operators.golden_images.constants import (
    COMMON_TEMPLATE,
    CUSTOM_TEMPLATE,
    DATA_IMPORT_SCHEDULE_RANDOM_MINUTES_REGEX,
    EXPECTED_DEFAULT_ARCHITECTURES,
    RE_NAMED_GROUP_HOURS,
    RE_NAMED_GROUP_MINUTES,
)
from tests.install_upgrade_operators.golden_images.multi_arch.utils import assert_sets_equal
from utilities.constants import SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME, TIMEOUT_10MIN

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


def verify_data_import_cron_template_status_in_hco_cr(hco_status_templates):
    mismatch_errors = {}
    for template in hco_status_templates:
        original_supported_architectures = template["status"]["originalSupportedArchitectures"].split(",")
        if set(original_supported_architectures) != set(EXPECTED_DEFAULT_ARCHITECTURES):
            mismatch_errors[template["metadata"]["name"]] = (
                f"expected: {EXPECTED_DEFAULT_ARCHITECTURES}, actual: {original_supported_architectures}"
            )

    assert not mismatch_errors, f"Templates with mismatching architectures: {mismatch_errors}"


def verify_resource_in_ns(
    expected_resource_names: set[str],
    namespace: str,
    client: DynamicClient,
    resource_type: Resource,
    ready_condition: str | None = None,
    resource_list: list[Resource] | None = None,
) -> None:
    """
    Verify that resources exist in the namespace and optionally reach a ready condition.

    Args:
        expected_resource_names: Expected resource names.
        namespace: Namespace to check.
        client: Kubernetes dynamic client.
        resource_type: Resource type class to query.
        ready_condition: Condition to wait for on each resource.
        resource_list: List of resources to check.
    """
    resources = resource_list or resource_type.get(client=client, namespace=namespace)
    assert_sets_equal(
        actual={resource.name for resource in resources},
        expected=expected_resource_names,
    )

    if ready_condition:
        for resource in resources:
            resource.wait_for_condition(
                condition=ready_condition,
                status=resource.Condition.Status.TRUE,
                timeout=TIMEOUT_10MIN,
            )


def get_templates_resources_names_dict(templates: list[dict[str, Any]]) -> dict[str, set[str]]:
    """
    Extract base resource names from DataImportCronTemplates.

    Args:
        templates: List of DataImportCronTemplate dicts from HCO status.

    Returns:
        Dictionary with resource kinds as keys and sets of names as values.
        Keys include DataImportCron.kind, DataSource.kind, and optionally ImageStream.kind.
    """
    resource_dict: dict[str, set[str]] = {}
    for template in templates:
        if image_stream_name := template["spec"]["template"]["spec"]["source"]["registry"].get("imageStream"):
            resource_dict.setdefault(ImageStream.kind, set()).add(image_stream_name)
        resource_dict.setdefault(DataImportCron.kind, set()).add(template["metadata"]["name"])
        resource_dict.setdefault(DataSource.kind, set()).add(template["spec"]["managedDataSource"])
    return resource_dict


def verify_data_import_cron_template_annotation(template: dict[str, Any], expected_architectures: set[str]) -> None:
    assert_sets_equal(
        actual=set(template["metadata"]["annotations"].get("ssp.kubevirt.io/dict.architectures").split(",")),
        expected=expected_architectures,
    )
