"""
Pytest conftest file for CNV tests
"""

import logging
import multiprocessing
import os
from datetime import UTC, datetime
from signal import SIGINT, SIGTERM, getsignal, signal

import pytest
from ocp_resources.datavolume import DataVolume
from packaging.version import parse
from pytest_testconfig import config as py_config

import utilities.hco
from libs.net.cluster import supported_cluster_ip_versions
from libs.net.ip import filter_link_local_addresses, random_cidr_addresses_by_family
from libs.net.vmspec import lookup_iface_status
from utilities.constants.cluster import (
    NODE_TYPE_WORKER_LABEL,
)
from utilities.constants.hco import (
    HOTFIX_STR,
    UpgradeStreams,
)
from utilities.constants.networking import LINUX_BRIDGE
from utilities.constants.storage import BIND_IMMEDIATE_ANNOTATION
from utilities.constants.virt import ES_NONE
from utilities.infra import (
    create_ns,
    get_clusterversion,
    get_node_selector_dict,
)
from utilities.network import (
    cloud_init_network_data,
    network_device,
    network_nad,
    wait_for_node_marked_by_bridge,
)
from utilities.operator import (
    get_hco_csv_name_by_version,
)
from utilities.storage import (
    construct_datavolume_source_dict,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
    vm_instance_from_template,
)

LOGGER = logging.getLogger(__name__)
CNV_NOT_INSTALLED = "CNV not yet installed."


@pytest.fixture(scope="module")
def multiprocessing_start_method_fork():
    """Temporarily set multiprocessing start method to ``fork``.

    Side effects:
        Changes the process-global multiprocessing start method to ``fork``
        for the module lifetime, then restores the previous method on teardown.
    """
    # https://docs.python.org/3/library/multiprocessing.html#multiprocessing.Process
    # https://github.com/python/cpython/issues/132898
    original_start_method = multiprocessing.get_start_method()
    multiprocessing.set_start_method("fork", force=True)
    yield
    multiprocessing.set_start_method(original_start_method, force=True)


@pytest.fixture(scope="session")
def junitxml_polarion(record_testsuite_property):
    """
    Add polarion needed attributes to junit xml

    export as os environment:
    POLARION_CUSTOM_PLANNEDIN
    POLARION_TESTRUN_ID
    POLARION_TIER
    """
    record_testsuite_property("polarion-custom-isautomated", "True")
    record_testsuite_property("polarion-testrun-status-id", "inprogress")
    record_testsuite_property("polarion-custom-plannedin", os.getenv("POLARION_CUSTOM_PLANNEDIN"))
    record_testsuite_property("polarion-user-id", "cnvqe")
    record_testsuite_property("polarion-project-id", "CNV")
    record_testsuite_property("polarion-response-myproduct", "cnv-test-run")
    record_testsuite_property("polarion-testrun-id", os.getenv("POLARION_TESTRUN_ID"))
    record_testsuite_property("polarion-custom-env_tier", os.getenv("POLARION_TIER"))
    record_testsuite_property("polarion-custom-env_os", os.getenv("POLARION_OS"))


@pytest.fixture(scope="session")
def session_start_time() -> datetime:
    """
    Capture when test session started in UTC.

    Uses UTC to match the timezone used in audit log file names.

    Returns:
        datetime: UTC timestamp when test session began (timezone-naive)
    """
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture(scope="session")
def openshift_current_version(admin_client):
    return get_clusterversion(client=admin_client).instance.status.history[0].version


@pytest.fixture(scope="session")
def ocp_current_version(openshift_current_version):
    return parse(version=openshift_current_version.split("-")[0])


@pytest.fixture()
def vm_instance_from_template_multi_storage_scope_function(
    request,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    cpu_for_migration,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_multi_storage_scope_function,
        vm_cpu_model=(cpu_for_migration if request.param.get("set_vm_common_cpu") else None),
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def junitxml_plugin(request, record_testsuite_property):
    return record_testsuite_property if request.config.pluginmanager.hasplugin("junitxml") else None


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
def upgrade_bridge_on_all_nodes(
    admin_client,
    label_schedulable_nodes,
    hosts_common_available_ports,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="upgrade-bridge",
        interface_name="br1upgrade",
        node_selector_labels=NODE_TYPE_WORKER_LABEL,
        ports=[hosts_common_available_ports[0]],
        client=admin_client,
    ) as br:
        yield br


@pytest.fixture(scope="session")
def bridge_on_one_node(admin_client, worker_node1):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="upgrade-br-marker",
        interface_name="upg-br-mark",
        node_selector=get_node_selector_dict(node_selector=worker_node1.name),
        client=admin_client,
    ) as br:
        yield br


@pytest.fixture(scope="session")
def upgrade_bridge_marker_nad(admin_client, bridge_on_one_node, kmp_enabled_namespace, worker_node1):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=bridge_on_one_node.bridge_name,
        interface_name=bridge_on_one_node.bridge_name,
        namespace=kmp_enabled_namespace,
        client=admin_client,
    ) as nad:
        wait_for_node_marked_by_bridge(bridge_nad=nad, node=worker_node1)
        yield nad


@pytest.fixture(scope="session")
def running_vm_upgrade_a(
    unprivileged_client,
    upgrade_bridge_marker_nad,
    kmp_enabled_namespace,
    upgrade_br1test_nad,
):
    name = "vm-upgrade-a"
    cloud_init_data = cloud_init_network_data(
        data={
            "ethernets": {
                "eth1": {
                    "addresses": [str(addr) for addr in random_cidr_addresses_by_family(net_seed=0, host_address=1)]
                }
            }
        }
    )
    with VirtualMachineForTests(
        name=name,
        namespace=kmp_enabled_namespace.name,
        networks={upgrade_bridge_marker_nad.name: upgrade_bridge_marker_nad.name},
        interfaces=[upgrade_bridge_marker_nad.name],
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
        body=fedora_vm_body(name=name),
        eviction_strategy=ES_NONE,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        ip_families = supported_cluster_ip_versions()
        lookup_iface_status(
            vm=vm,
            iface_name=upgrade_bridge_marker_nad.name,
            predicate=lambda interface: (
                len(filter_link_local_addresses(ip_addresses=interface.get("ipAddresses", []))) == len(ip_families)
            ),
        )
        yield vm


@pytest.fixture(scope="session")
def running_vm_upgrade_b(
    unprivileged_client,
    upgrade_bridge_marker_nad,
    kmp_enabled_namespace,
    upgrade_br1test_nad,
):
    name = "vm-upgrade-b"
    cloud_init_data = cloud_init_network_data(
        data={
            "ethernets": {
                "eth1": {
                    "addresses": [str(addr) for addr in random_cidr_addresses_by_family(net_seed=0, host_address=2)]
                }
            }
        }
    )
    with VirtualMachineForTests(
        name=name,
        namespace=kmp_enabled_namespace.name,
        networks={upgrade_bridge_marker_nad.name: upgrade_bridge_marker_nad.name},
        interfaces=[upgrade_bridge_marker_nad.name],
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
        body=fedora_vm_body(name=name),
        eviction_strategy=ES_NONE,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        ip_families = supported_cluster_ip_versions()
        lookup_iface_status(
            vm=vm,
            iface_name=upgrade_bridge_marker_nad.name,
            predicate=lambda interface: (
                len(filter_link_local_addresses(ip_addresses=interface.get("ipAddresses", []))) == len(ip_families)
            ),
        )
        yield vm


@pytest.fixture(scope="session")
def upgrade_br1test_nad(admin_client, upgrade_namespace_scope_session, upgrade_bridge_on_all_nodes):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=upgrade_bridge_on_all_nodes.bridge_name,
        interface_name=upgrade_bridge_on_all_nodes.bridge_name,
        namespace=upgrade_namespace_scope_session,
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="session")
def cnv_upgrade_stream(admin_client, pytestconfig, cnv_current_version, cnv_target_version):
    """
    Verify if the upgrade can be performed by comparing the current and target versions.

    Args:
        admin_client: The admin client instance.
        pytestconfig: The pytest configuration object.
        cnv_current_version: The current CNV version.
        cnv_target_version: The target CNV version.
    """
    upgrade_stream = determine_upgrade_stream(
        current_version=cnv_current_version,
        target_version=cnv_target_version,
    )

    LOGGER.info(
        f"CNV upgrade:\n"
        f"Current version: {cnv_current_version},\n"
        f"Target version: {cnv_target_version},\n"
        f"Upgrade stream: {upgrade_stream},\n"
    )
    return upgrade_stream


def determine_upgrade_stream(current_version, target_version):
    current_cnv_version = parse(version=current_version.split("-")[0])
    target_cnv_version = parse(version=target_version.split("-")[0])

    if current_cnv_version.major < target_cnv_version.major:
        return UpgradeStreams.X_STREAM
    elif current_cnv_version.minor < target_cnv_version.minor:
        return UpgradeStreams.Y_STREAM
    elif current_cnv_version.micro < target_cnv_version.micro:
        return UpgradeStreams.Z_STREAM
    elif HOTFIX_STR in current_version:
        # if we reach here, this is an upgrade out of hotfix to next z-stream
        return UpgradeStreams.Z_STREAM
    else:
        if target_cnv_version <= current_cnv_version:
            # Upgrade only if a newer CNV version is requested
            raise ValueError(
                f"Cannot upgrade to older/identical versions,"
                f"current: {current_cnv_version} target: {target_cnv_version}"
            )
        raise ValueError(
            f"Unknown upgrade stream. Current cnv version: {current_cnv_version}, "
            f"target cnv version: {target_cnv_version}."
        )


@pytest.fixture(scope="session")
def upgrade_namespace_scope_session(admin_client, unprivileged_client):
    yield from create_ns(
        unprivileged_client=unprivileged_client,
        admin_client=admin_client,
        name="test-upgrade-namespace",
    )


@pytest.fixture(scope="session")
def hco_target_csv_name(cnv_target_version):
    return get_hco_csv_name_by_version(cnv_target_version=cnv_target_version) if cnv_target_version else None


@pytest.fixture(scope="session")
def cnv_target_version(pytestconfig):
    return pytestconfig.option.cnv_version


@pytest.fixture(scope="session")
def cnv_channel(pytestconfig):
    return pytestconfig.option.cnv_channel


@pytest.fixture(autouse=True)
def autouse_fixtures(
    leftovers_cleanup,  # Must be called first to avoid deleting created resources.
    artifactory_setup,
    bin_directory_to_os_path,
    cluster_info,
    term_handler_scope_function,
    term_handler_scope_class,
    term_handler_scope_module,
    term_handler_scope_session,
    junitxml_polarion,
    admin_client,
    cluster_sanity_scope_session,
    cluster_sanity_scope_module,
    generated_ssh_key_for_vm_access,
    session_start_time,
):
    """call all autouse fixtures"""


@pytest.fixture(scope="session")
def installing_cnv(pytestconfig):
    return pytestconfig.option.install


@pytest.fixture(scope="session")
def is_production_source(cnv_source):
    return cnv_source == "production"


@pytest.fixture(scope="session")
def cnv_source(pytestconfig):
    return pytestconfig.option.cnv_source or "osbs"


@pytest.fixture(scope="session")
def upgrade_skip_default_sc_setup(pytestconfig):
    return pytestconfig.option.upgrade_skip_default_sc_setup


@pytest.fixture(scope="session")
def dvs_for_upgrade(
    admin_client,
    worker_node1,
    rhel_latest_os_params,
    updated_default_storage_class_ocs_virt,
):
    golden_images_namespace_name = py_config["golden_images_namespace"]
    dvs_list = []
    artifactory_secret = utilities.artifactory.get_artifactory_secret(namespace=golden_images_namespace_name)
    artifactory_config_map = utilities.artifactory.get_artifactory_config_map(namespace=golden_images_namespace_name)

    for sc in py_config["storage_class_matrix"]:
        storage_class = [*sc][0]
        dv = DataVolume(
            client=admin_client,
            name=f"dv-for-product-upgrade-{storage_class}",
            namespace=golden_images_namespace_name,
            source_dict=construct_datavolume_source_dict(
                source="http",
                url=rhel_latest_os_params["rhel_image_path"],
                secret_name=artifactory_secret.name,
                cert_configmap_name=artifactory_config_map.name,
            ),
            storage_class=storage_class,
            size=rhel_latest_os_params["rhel_dv_size"],
            annotations=BIND_IMMEDIATE_ANNOTATION,
            api_name="storage",
        )
        dv.create()
        dvs_list.append(dv)
    for dv in dvs_list:
        dv.wait_for_dv_success()

    yield dvs_list

    for dv in dvs_list:
        dv.clean_up()
    utilities.artifactory.cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret,
        artifactory_config_map=artifactory_config_map,
    )


# TODO: Replace this fixture with py_config.get("conformance_tests")
@pytest.fixture(scope="session")
def conformance_tests(request):
    return (
        (marker_args := request.config.getoption("-m"))
        and "conformance" in marker_args
        and "not conformance" not in marker_args
    )
