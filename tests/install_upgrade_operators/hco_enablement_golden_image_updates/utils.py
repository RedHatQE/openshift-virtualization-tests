import logging
import re

from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.data_import_cron import DataImportCron

from tests.install_upgrade_operators.constants import CUSTOM_DATASOURCE_NAME
from utilities.constants import (
    OUTDATED,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
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
        "managedDataSource": CUSTOM_DATASOURCE_NAME,
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


def get_data_import_cron_by_name(namespace, cron_name):
    data_import_cron = DataImportCron(name=cron_name, namespace=namespace)
    if data_import_cron.exists:
        return data_import_cron
    raise ResourceNotFoundError(f"DataImportCron: {data_import_cron} not found in namespace: {namespace}")


def get_template_dict_by_name(template_name, templates):
    for template in templates:
        if template["metadata"]["name"] == template_name:
            return template
