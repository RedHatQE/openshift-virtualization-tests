import os
import logging
from signal import SIGINT, SIGTERM, getsignal, signal

import pytest
from pytest_testconfig import config as py_config
import ipaddress

from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.network import Network
from ocp_resources.node import Node
from ocp_resources.storage_class import StorageClass
from ocp_utilities.infra import get_client
from utilities.constants import (
    StorageClassNames,
    VIRTCTL_CLI_DOWNLOADS,
    NamespacesNames,
)
from utilities.hco import get_hyperconverged_resource
from utilities.infra import (
    get_namespace,
    run_virtctl_command,
    get_clusterversion,
    cluster_sanity,
    download_file_from_cluster,
)
from utilities.network import get_cluster_cni_type
from utilities.operator import (
    get_cnv_installed_csv,
    get_subscription,
    get_catalog_source,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def admin_client():
    """
    Get DynamicClient
    """
    return get_client()


@pytest.fixture(scope="session")
def openshift_cnv_namespace():
    return get_namespace(name=py_config["cnv_namespace"])


@pytest.fixture(scope="session")
def os_path_environment():
    return os.environ["PATH"]


@pytest.fixture(scope="session")
def bin_directory(tmpdir_factory):
    return tmpdir_factory.mktemp("bin")


@pytest.fixture(scope="session")
def virtctl_binary(os_path_environment, bin_directory):
    installed_virtctl = os.environ.get("CNV_TESTS_VIRTCTL_BIN")
    if installed_virtctl:
        LOGGER.warning(f"Using previously installed: {installed_virtctl}")
        return
    return download_file_from_cluster(
        get_console_spec_links_name=VIRTCTL_CLI_DOWNLOADS, dest_dir=bin_directory
    )


@pytest.fixture(scope="session")
def oc_binary(os_path_environment, bin_directory):
    installed_oc = os.environ.get("CNV_TESTS_OC_BIN")
    if installed_oc:
        LOGGER.warning(f"Using previously installed: {installed_oc}")
        return
    return download_file_from_cluster(
        get_console_spec_links_name="oc-cli-downloads", dest_dir=bin_directory
    )


@pytest.fixture(scope="session")
def openshift_cnv_csv_scope_session(openshift_cnv_namespace):
    return get_cnv_installed_csv(
        namespace=openshift_cnv_namespace.name,
        subscription_name=py_config["hco_subscription"],
    )


@pytest.fixture(scope="session")
def bin_directory_to_os_path(
    os_path_environment, bin_directory, virtctl_binary, oc_binary
):
    LOGGER.info(f"Adding {bin_directory} to $PATH")
    os.environ["PATH"] = f"{bin_directory}:{os_path_environment}"


@pytest.fixture(scope="session")
def hco_namespace():
    return get_namespace(name=py_config["cnv_namespace"])


@pytest.fixture(scope="session")
def cnv_csv_scope_session(hco_namespace):
    return get_cnv_installed_csv(
        subscription_name=py_config["hco_subscription"], namespace=hco_namespace.name
    )


@pytest.fixture(scope="session")
def hco_scope_session():
    return get_hyperconverged_resource(namespace_name=py_config["cnv_namespace"])


@pytest.fixture(scope="session")
def cnv_subscription_scope_session(
    hco_namespace,
):
    return get_subscription(
        namespace=hco_namespace.name,
        subscription_name=py_config["hco_subscription"],
    )


@pytest.fixture(scope="session")
def hco_image_from_catalog_source(
    cnv_subscription_scope_session,
):
    return get_catalog_source(
        catalogsource_name=cnv_subscription_scope_session.instance.spec.source
    ).instance.spec.image


@pytest.fixture(scope="session")
def cluster_storage_classes(admin_client):
    return list(StorageClass.get(dyn_client=admin_client))


@pytest.fixture(scope="session")
def ocs_storage_class(cluster_storage_classes):
    for sc in cluster_storage_classes:
        if sc.name == StorageClassNames.CEPH_RBD_VIRTUALIZATION:
            return sc


@pytest.fixture(scope="session")
def cluster_service_network():
    return Network(name="cluster").instance.status.serviceNetwork


@pytest.fixture(scope="session")
def ipv4_supported_cluster(cluster_service_network):
    if cluster_service_network:
        return any(
            [ipaddress.ip_network(ip).version == 4 for ip in cluster_service_network]
        )


@pytest.fixture(scope="session")
def ipv6_supported_cluster(cluster_service_network):
    if cluster_service_network:
        return any(
            [ipaddress.ip_network(ip).version == 6 for ip in cluster_service_network]
        )


@pytest.fixture(scope="session")
def ocs_current_version(ocs_storage_class, admin_client):
    if ocs_storage_class:
        for csv in ClusterServiceVersion.get(
            dyn_client=admin_client,
            namespace=NamespacesNames.OPENSHIFT_STORAGE,
            label_selector=f"{ClusterServiceVersion.ApiGroup.OPERATORS_COREOS_COM}/ocs-operator.openshift-storage",
        ):
            return csv.instance.spec.version


@pytest.fixture(scope="session")
def cluster_info(
    admin_client,
    openshift_current_version,
    cnv_csv_scope_session,
    hco_scope_session,
    hco_image_from_catalog_source,
    ocs_current_version,
    ipv6_supported_cluster,
    ipv4_supported_cluster,
):
    title = "\nCluster info:\n"

    virtctl_client_version, virtctl_server_version = (
        run_virtctl_command(command=["version"])[1].strip().splitlines()
    )

    LOGGER.info(
        f"{title}"
        f"\tOpenshift version: {openshift_current_version}\n"
        f"\tCNV CSV version: {cnv_csv_scope_session.instance.spec.version}\n"
        f"\tHCO version: {hco_scope_session.instance.status.versions[0].version}\n"
        f"\tHCO image: {hco_image_from_catalog_source}\n"
        f"\tOCS version: {ocs_current_version}\n"
        f"\tCNI type: {get_cluster_cni_type(admin_client=admin_client)}\n"
        f"\tIPv4 cluster: {ipv4_supported_cluster}\n"
        f"\tIPv6 cluster: {ipv6_supported_cluster}\n"
        f"\tVirtctl version: \n\t{virtctl_client_version}\n\t{virtctl_server_version}\n"
    )


@pytest.fixture(scope="session")
def openshift_current_version(admin_client):
    return (
        get_clusterversion(dyn_client=admin_client).instance.status.history[0].version
    )


@pytest.fixture
def term_handler_scope_function():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="class")
def term_handler_scope_class():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="module")
def term_handler_scope_module():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="session")
def term_handler_scope_session():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="session")
def nodes(admin_client):
    yield list(Node.get(dyn_client=admin_client))


@pytest.fixture(scope="session")
def cluster_sanity_scope_session(
    nodes,
    admin_client,
    hco_namespace,
):
    """
    Performs various cluster level checks, e.g.: storage class validation, node state, as well as all cnv pod
    check to ensure all are in 'Running' state, to determine current state of cluster
    """
    cluster_sanity(
        admin_client=admin_client,
        nodes=nodes,
        hco_namespace=hco_namespace.name,
    )


@pytest.fixture(scope="module")
def cluster_sanity_scope_module(
    nodes,
    admin_client,
    hco_namespace,
):
    cluster_sanity(
        admin_client=admin_client,
        nodes=nodes,
        hco_namespace=hco_namespace.name,
    )


@pytest.fixture(autouse=True)
@pytest.mark.early(order=0)
def autouse_fixtures(
    bin_directory_to_os_path,
    cluster_info,
    term_handler_scope_function,
    term_handler_scope_class,
    term_handler_scope_module,
    term_handler_scope_session,
    admin_client,
    cluster_sanity_scope_session,
    cluster_sanity_scope_module,
):
    """call all autouse fixtures"""
