import logging

import pytest
from ocp_resources.ingress_config_openshift_io import Ingress
from ocp_resources.resource import ResourceEditor
from ocp_resources.route import Route

from tests.install_upgrade_operators.console_cli_download.utils import validate_custom_cli_downloads_urls_updated
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
def all_virtctl_urls_scope_function(admin_client):
    return get_all_console_links(
        console_cli_downloads_spec_links=get_console_spec_links(admin_client=admin_client, name=VIRTCTL_CLI_DOWNLOADS)
    )


@pytest.fixture(scope="class")
def all_virtctl_urls_scope_class(admin_client):
    return get_all_console_links(
        console_cli_downloads_spec_links=get_console_spec_links(admin_client=admin_client, name=VIRTCTL_CLI_DOWNLOADS)
    )


@pytest.fixture()
def internal_fqdn(admin_client, hco_namespace):
    """
    This fixture returns the prefix url for the cluster, which is used to identify if certain links are routed or
    served from within the cluster
    """
    cluster_route = Route(name=HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD, namespace=hco_namespace.name, client=admin_client)
    assert cluster_route.exists
    return cluster_route.instance.spec.host


@pytest.fixture()
def non_internal_fqdns(all_virtctl_urls_scope_function, internal_fqdn):
    """
    Get URLs containing FQDN that is not matching the cluster's route

    Returns:
        list: list of all non-internal FQDNs
    """
    return [virtctl_url for virtctl_url in all_virtctl_urls_scope_function if f"//{internal_fqdn}" not in virtctl_url]


@pytest.fixture()
def downloaded_and_extracted_virtctl_binary_for_os(request, all_virtctl_urls_scope_function, tmpdir):
    """
    This fixture downloads the virtctl archive from the provided OS, and extracts it to a temporary dir
    """
    return get_and_extract_file_from_cluster(
        system_os=request.param.get("os"),
        urls=all_virtctl_urls_scope_function,
        dest_dir=tmpdir,
        machine_type=request.param.get("machine_type"),
    )


@pytest.fixture(scope="class")
def updated_cluster_ingress_downloads_spec_links(request, admin_client, hco_namespace, all_virtctl_urls_scope_class):
    ingress_resource = Ingress(client=admin_client, name="cluster", ensure_exists=True)
    ingress_resource_instance = ingress_resource.instance
    component_routes_cnv = None
    for component_route in ingress_resource_instance.status.componentRoutes:
        if component_route.namespace == hco_namespace.name:
            component_routes_cnv = component_route
            break
    assert component_routes_cnv, (
        f"No CNV componentRoute found under ingress.status.componentRoutes for namespace '{hco_namespace.name}', "
        "Cannot patch cluster ingress for console CLI downloads."
    )
    component_routes_to_update = {
        "componentRoutes": [
            {
                "hostname": f"{request.param['new_hostname']}.{ingress_resource_instance.spec.domain}",
                "name": component_routes_cnv["name"],
                "namespace": hco_namespace.name,
            }
        ],
    }

    with ResourceEditor(patches={ingress_resource: {"spec": component_routes_to_update}}):
        yield
    validate_custom_cli_downloads_urls_updated(
        admin_client=admin_client,
        original_links=all_virtctl_urls_scope_class,
    )
