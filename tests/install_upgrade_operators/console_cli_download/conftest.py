import logging

import pytest
from ocp_resources.route import Route

from utilities.constants import (
    HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
    VIRTCTL_CLI_DOWNLOADS,
)
from utilities.infra import (
    get_all_console_links,
    get_and_extract_file_from_cluster,
    get_console_spec_links,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def virtctl_console_cli_downloads_spec_links(admin_client):
    """
    Get console cli downloads spec links

    Returns:
        ConsoleCLIDownload instance.spec.links
    """
    return get_console_spec_links(admin_client=admin_client, name=VIRTCTL_CLI_DOWNLOADS)


@pytest.fixture()
def all_virtctl_urls(virtctl_console_cli_downloads_spec_links):
    """This fixture returns URLs for the various OSs to download virtctl"""
    return get_all_console_links(console_cli_downloads_spec_links=virtctl_console_cli_downloads_spec_links)


@pytest.fixture()
def internal_fqdn(admin_client, hco_namespace):
    """
    This fixture returns the prefix url for the cluster, which is used to identify if certain links are routed or
    served from within the cluster
    """
    cluster_route = Route(name=HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD, namespace=hco_namespace.name)
    assert cluster_route.exists
    return cluster_route.instance.spec.host


@pytest.fixture()
def non_internal_fqdns(all_virtctl_urls, internal_fqdn):
    """
    Get URLs containing FQDN that is not matching the cluster's route

    Returns:
        list: list of all non-internal FQDNs
    """
    return [virtctl_url for virtctl_url in all_virtctl_urls if f"//{internal_fqdn}" not in virtctl_url]


@pytest.fixture()
def downloaded_and_extracted_virtctl_binary_for_os(request, all_virtctl_urls, tmpdir):
    """
    This fixture downloads the virtctl archive from the provided OS, and extracts it to a temporary dir
    """
    return get_and_extract_file_from_cluster(
        system_os=request.param.get("os"),
        urls=all_virtctl_urls,
        dest_dir=tmpdir,
        machine_type=request.param.get("machine_type"),
    )
