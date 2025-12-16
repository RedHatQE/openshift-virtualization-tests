import logging
import re

import requests
from bs4 import BeautifulSoup
from kubernetes.dynamic import DynamicClient
from ocp_resources.data_source import DataSource
from ocp_resources.namespace import Namespace
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.template import Template
from ocp_resources.volume_snapshot import VolumeSnapshot
from packaging.version import Version
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.infrastructure.golden_images.constants import (
    DEFAULT_FEDORA_REGISTRY_URL,
)
from utilities.constants import (
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_30SEC,
    WILDCARD_CRON_EXPRESSION,
)
from utilities.infra import generate_openshift_pull_secret_file
from utilities.ssp import (
    get_data_import_crons,
    matrix_auto_boot_data_import_cron_prefixes,
)
from utilities.storage import (
    DATA_IMPORT_CRON_SUFFIX,
    RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL,
)
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
    Retrieve all DataImportCron-managed volume names from a namespace.

    The function fetches both PersistentVolumeClaims and VolumeSnapshots that are
    managed by DataImportCron (identified by the appropriate label selector) and
    returns their names.

    Args:
        client (DynamicClient): Dynamic client for resource queries.
        namespace (str): The namespace to search for volumes.

    Returns:
        list[str]: Combined list of PVC and VolumeSnapshot names managed by DataImportCron.
    """

    def _fetch_volume_names(resource_cls: type[PersistentVolumeClaim] | type[VolumeSnapshot]) -> list[str]:
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
    except (ValueError, AttributeError, TypeError):
        LOGGER.warning(f"No RHEL version was found from: {image}")
        return None


def wait_for_existing_auto_update_data_import_crons(admin_client: DynamicClient, namespace: Namespace) -> None:
    """
    Wait for all expected auto-update DataImportCrons to be created in the namespace.

    The function polls for the presence of DataImportCrons matching the expected
    auto-boot prefixes and returns when all are found or raises TimeoutExpiredError
    if any are missing after the timeout period.

    Args:
        admin_client (DynamicClient): Admin client for resource queries.
        namespace (Namespace): The namespace to check for DataImportCrons.

    Raises:
        TimeoutExpiredError: If not all expected DataImportCrons are created within 2 minutes.
    """

    def _get_missing_data_import_crons(
        _client: DynamicClient, _namespace: Namespace, _auto_boot_data_import_cron_prefixes: list[str]
    ) -> list[str]:
        data_import_crons = get_data_import_crons(admin_client=_client, namespace=_namespace)

        extract_existing_dic_prefixes = {re.sub(DATA_IMPORT_CRON_SUFFIX, "", dic.name) for dic in data_import_crons}

        return list(set(_auto_boot_data_import_cron_prefixes) - extract_existing_dic_prefixes)

    sample = None
    auto_boot_data_import_cron_prefixes = matrix_auto_boot_data_import_cron_prefixes()
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
            func=_get_missing_data_import_crons,
            _client=admin_client,
            _namespace=namespace,
            _auto_boot_data_import_cron_prefixes=auto_boot_data_import_cron_prefixes,
        ):
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Some dataImportCron resources are missing: {sample}")
        raise


def wait_for_created_volume_from_data_import_cron(custom_data_source: DataSource) -> None:
    """
    Wait for a DataImportCron to create a volume referenced by a DataSource.

    The function polls the DataSource's source reference and waits until it exists,
    indicating that the DataImportCron has successfully created the backing volume.

    Args:
        custom_data_source (DataSource): The DataSource resource to monitor for volume creation.

    Raises:
        TimeoutExpiredError: If the volume is not created within 5 minutes.
    """
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: custom_data_source.source.exists,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Volume was not created under {custom_data_source.namespace} namespace, "
            f"DataSource conditions: {custom_data_source.instance.get('status', {}).get('conditions')}"
        )
        raise
