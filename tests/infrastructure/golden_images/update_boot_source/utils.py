import logging

from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.template import Template
from ocp_resources.volume_snapshot import VolumeSnapshot

from tests.infrastructure.golden_images.constants import (
    DEFAULT_FEDORA_REGISTRY_URL,
)
from utilities.constants import WILDCARD_CRON_EXPRESSION
from utilities.storage import RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL

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


def get_all_dic_volume_names(client, namespace):
    def _fetch_volume_names(resource_cls):
        return [
            volume.name
            for volume in resource_cls.get(
                client=client,
                namespace=namespace,
                label_selector=RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL,
            )
            if volume.exists
        ]

    return _fetch_volume_names(PersistentVolumeClaim) + _fetch_volume_names(VolumeSnapshot)
