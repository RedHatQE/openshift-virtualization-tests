import pytest
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import config as py_config

from libs.net.cluster import supported_cluster_ip_versions
from libs.net.ip import filter_link_local_addresses, random_cidr_addresses_by_family
from libs.net.vmspec import lookup_iface_status
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
)
from utilities.constants.cluster import NODE_TYPE_WORKER_LABEL
from utilities.constants.networking import LINUX_BRIDGE
from utilities.constants.storage import BIND_IMMEDIATE_ANNOTATION
from utilities.constants.virt import ES_NONE
from utilities.infra import create_ns, get_node_selector_dict
from utilities.network import cloud_init_network_data, network_device, network_nad, wait_for_node_marked_by_bridge
from utilities.storage import construct_datavolume_source_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.fixture(scope="session")
def upgrade_namespace_scope_session(admin_client, unprivileged_client):
    yield from create_ns(
        unprivileged_client=unprivileged_client,
        admin_client=admin_client,
        name="test-upgrade-namespace",
    )


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
def running_vm_upgrade_a(
    unprivileged_client,
    upgrade_bridge_marker_nad,
    kmp_enabled_namespace,
    upgrade_br1test_nad,
):
    name = "vm-upgrade-a"
    cloud_init_data = cloud_init_network_data(
        data={"ethernets": {"eth1": {"addresses": random_cidr_addresses_by_family(net_seed=0, host_address=1)}}}
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
        data={"ethernets": {"eth1": {"addresses": random_cidr_addresses_by_family(net_seed=0, host_address=2)}}}
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
def dvs_for_upgrade(
    admin_client,
    worker_node1,
    rhel_latest_os_params,
    updated_default_storage_class_ocs_virt,
):
    golden_images_namespace_name = py_config["golden_images_namespace"]
    dvs_list = []
    artifactory_secret = get_artifactory_secret(namespace=golden_images_namespace_name)
    artifactory_config_map = get_artifactory_config_map(namespace=golden_images_namespace_name)

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
    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret,
        artifactory_config_map=artifactory_config_map,
    )
