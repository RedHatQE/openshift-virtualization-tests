import logging

from kubernetes.dynamic import DynamicClient
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_1MIN, TIMEOUT_5SEC, VIRTCTL_CLI_DOWNLOADS
from utilities.infra import get_console_spec_links

LOGGER = logging.getLogger(__name__)
CUSTOMIZED_VIRT_DL = "customized-virt-dl"


def validate_custom_cli_downloads_urls_updated(
    admin_client: DynamicClient,
    new_hostname: str | None = None,
    original_links: list[str] | None = None,
) -> None:
    """
    Validates that console CLI download URLs have been properly updated.

    This function monitors the console CLI download links and validates one of two scenarios:
    1. URLs have been reverted to their original state (rollback validation)
    2. URLs have been updated to use a new hostname (update validation)

    Args:
        admin_client (DynamicClient): Kubernetes dynamic client for API operations
        new_hostname (str, optional): New hostname that should be present in all URLs.
            If provided, validates that all URLs contain this hostname.
            Mutually exclusive with original_virtctl_console_cli_downloads_spec_links.
        original_links (list[str], optional):
            Original list of CLI download URLs. If provided, validates that current
            URLs match these original URLs.
            Mutually exclusive with new_hostname.

    Raises:
        TimeoutExpiredError: If validation fails within the timeout period (1 minute).
            This can occur when:
            - URLs don't revert to original state within timeout
            - URLs don't get updated with new hostname within timeout
        ValueError: If both new_hostname and original_virtctl_console_cli_downloads_spec_links
            are provided, or if neither is provided.
    """
    if (new_hostname is None) == (original_links is None):
        raise ValueError(
            "Exactly one of 'new_hostname' or 'original_virtctl_console_cli_downloads_spec_links' "
            "must be provided, not both or neither."
        )

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
            if original_links:
                if sorted(current_cli_spec_links) == sorted(original_links):
                    return
            elif new_hostname:
                urls_not_updated_with_new_hostname = [url for url in current_cli_spec_links if new_hostname not in url]
                if not urls_not_updated_with_new_hostname:
                    return
    except TimeoutExpiredError:
        if original_links:
            LOGGER.error(
                f"Failed to update cluster ingress downloads spec links to the original links: "
                f"original_cli_spec_links: {original_links}, "
                f"current_cli_spec_links: {current_cli_spec_links}"
            )
        else:
            LOGGER.error(
                f"Failed to get console spec links: {current_cli_spec_links}, "
                f"There are urls that are not updated with new hostname: {urls_not_updated_with_new_hostname}"
            )
        raise
