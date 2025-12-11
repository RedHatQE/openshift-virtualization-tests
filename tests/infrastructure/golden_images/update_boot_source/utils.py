import logging
import re

import requests
from bs4 import BeautifulSoup
from kubernetes.dynamic import DynamicClient
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.template import Template
from ocp_resources.volume_snapshot import VolumeSnapshot
from packaging.version import Version

from tests.infrastructure.golden_images.constants import (
    DEFAULT_FEDORA_REGISTRY_URL,
)
from utilities.constants import TIMEOUT_30SEC, WILDCARD_CRON_EXPRESSION
from utilities.infra import generate_openshift_pull_secret_file
from utilities.storage import RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL
from utilities.virt import get_oc_image_info

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


def get_all_dic_volume_names(client: DynamicClient, namespace: str) -> list[str]:
    """
    Retrieve all volume names (PVCs and VolumeSnapshots) managed by DataImportCrons.

    Fetches PersistentVolumeClaims and VolumeSnapshots in the specified namespace
    that are labeled as managed by DataImportCrons and returns their names.

    Args:
        client: Kubernetes dynamic client for API operations.
        namespace: Namespace to search for volumes.

    Returns:
        List of volume names (strings) from both PVCs and VolumeSnapshots.
    """

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


def get_all_release_versions_from_docs(major_ver_num: int) -> list[int]:
    """
    Parse the documentation index page to get all release notes versions.

    Fetches the Red Hat Enterprise Linux documentation index page for the specified
    major version and extracts all available minor release version numbers from
    the release notes links.

    Args:
        major_ver_num: Major version number (e.g., 8, 9, 10).

    Returns:
        Sorted list of minor version numbers (e.g., [0, 1, 2, 3, 4, 5, 6, 7]).

    Raises:
        requests.RequestException: If the HTTP request to the documentation page fails.
    """
    url = f"https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/{major_ver_num}/"
    response = requests.get(url=url, timeout=TIMEOUT_30SEC)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    versions = []
    pattern = re.compile(
        rf"/en/documentation/red_hat_enterprise_linux/{major_ver_num}/html/{major_ver_num}\.(\d+)_release_notes"
    )

    for link in soup.find_all("a", href=True):
        match = pattern.search(string=link.get("href", ""))
        if match:
            versions.append(int(match.group(1)))
    versions = sorted(set(versions))
    return versions


def get_image_version(image: str) -> str | None:
    """
    Extract the major.minor version from an image's version label.

    Retrieves image information and extracts the version label, returning
    only the major and minor version components (e.g., "8.9" from "8.9.0").

    Args:
        image: Image reference string.

    Returns:
        Version string in "major.minor" format (e.g., "8.9"), or None if:
        - The image information cannot be retrieved
        - The version label is not present in the image metadata
    """
    image_info = get_oc_image_info(
        image=image,
        pull_secret=generate_openshift_pull_secret_file(),
    )
    full_version = image_info.get("config", {}).get("config", {}).get("Labels", {}).get("version")
    try:
        version = Version(version=full_version)
        return f"{version.major}.{version.minor}"
    except ValueError | AttributeError | TypeError:  # type: ignore[misc]
        LOGGER.warning(f"No RHEL version was found from: {image}")
        return None
