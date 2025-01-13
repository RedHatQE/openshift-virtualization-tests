import logging

from ocp_resources.template import Template

from tests.infrastructure.golden_images.constants import (
    DEFAULT_FEDORA_REGISTRY_URL,
)
from utilities.constants import WILDCARD_CRON_EXPRESSION

LOGGER = logging.getLogger(__name__)


def generate_data_import_cron_dict(
    name,
    source_url=None,
    managed_data_source_name=None,
):
    return {
        "metadata": {
            "name": name,
            "annotations": {"cdi.kubevirt.io/storage.bind.immediate.requested": "true"},
        },
        "spec": {
            "retentionPolicy": "None",
            "managedDataSource": managed_data_source_name or "custom-data-source",
            "schedule": WILDCARD_CRON_EXPRESSION,
            "template": {
                "spec": {
                    "source": {
                        "registry": {
                            "url": source_url or DEFAULT_FEDORA_REGISTRY_URL,
                            "pullMethod": "node",
                        }
                    },
                    "storage": {"resources": {"requests": {"storage": "10Gi"}}},
                }
            },
        },
    }


def template_labels(os):
    return Template.generate_template_labels(
        os=os,
        workload=Template.Workload.SERVER,
        flavor=Template.Flavor.SMALL,
    )
