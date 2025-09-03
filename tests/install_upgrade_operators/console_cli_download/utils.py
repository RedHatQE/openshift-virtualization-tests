import logging

from _pytest._py.path import LocalPath
from kubernetes.dynamic import DynamicClient
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_1MIN, TIMEOUT_5SEC, VIRTCTL_CLI_DOWNLOADS
from utilities.infra import download_and_extract_file_from_cluster, get_console_spec_links

LOGGER = logging.getLogger(__name__)
CUSTOMIZED_VIRT_DL = "customized-virt-dl"


def validate_custom_cli_downloads_urls_updated(admin_client: DynamicClient, new_hostname: str) -> None:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=get_console_spec_links,
        admin_client=admin_client,
        name=VIRTCTL_CLI_DOWNLOADS,
    )
    urls_not_updated_with_new_hostname = None
    current_cli_spec_links = None
    try:
        for sample in samples:
            current_cli_spec_links = [url.href for url in sample]
            urls_not_updated_with_new_hostname = [url for url in current_cli_spec_links if new_hostname not in url]
            if not urls_not_updated_with_new_hostname:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Failed to get console spec links: {current_cli_spec_links}")
        LOGGER.error(f"There are urls that are not updated with new hostname: {urls_not_updated_with_new_hostname}")
        raise


def validate_custom_cli_urls_downloaded(urls: list[str], dest_dir: LocalPath) -> None:
    for url in urls:
        extracted_files = download_and_extract_file_from_cluster(tmpdir=dest_dir, url=url)
        assert extracted_files, f"url {url} is not valid."
