import pytest

from tests.network.connectivity.utils import create_running_vm
from utilities.constants import LINUX_BRIDGE, OVS_BRIDGE
from utilities.infra import get_node_selector_dict, name_prefix
from utilities.network import network_device, network_nad


@pytest.fixture(scope="module")
def bridge_device_name(index_number):
    yield f"br{next(index_number)}test"


@pytest.fixture(scope="module")
def vlan_id_1(vlan_index_number):
    return next(vlan_index_number)


@pytest.fixture(scope="module")
def vlan_id_2(vlan_index_number):
    return next(vlan_index_number)


@pytest.fixture(scope="module")
def vlan_id_3(vlan_index_number):
    return next(vlan_index_number)


@pytest.fixture()
def fail_if_not_ipv6_supported_cluster(ipv6_supported_cluster):
    if not ipv6_supported_cluster:
        pytest.fail(reason="IPv6 is not supported in this cluster")


@pytest.fixture(scope="class")
def nncp_linux_bridge_device_worker_1_source(
    nodes_available_nics,
    worker_node1,
    bridge_device_name,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"linux-bridge-{name_prefix(worker_node1.name)}",
        interface_name=bridge_device_name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.name][-1]],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def nncp_ovs_bridge_device_worker_1_source(
    nodes_available_nics,
    worker_node1,
    bridge_device_name,
):
    with network_device(
        interface_type=OVS_BRIDGE,
        nncp_name=f"ovs-bridge-{name_prefix(worker_node1.name)}",
        interface_name=bridge_device_name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.name][-1]],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def nncp_linux_bridge_device_worker_2_destination(
    nodes_available_nics,
    worker_node2,
    bridge_device_name,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"linux-bridge-{name_prefix(worker_node2.name)}",
        interface_name=bridge_device_name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[nodes_available_nics[worker_node2.name][-1]],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def nncp_ovs_bridge_device_worker_2_destination(
    nodes_available_nics,
    worker_node2,
    bridge_device_name,
):
    with network_device(
        interface_type=OVS_BRIDGE,
        nncp_name=f"ovs-bridge-{name_prefix(worker_node2.name)}",
        interface_name=bridge_device_name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[nodes_available_nics[worker_node2.name][-1]],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def nad_linux_bridge(
    namespace,
    nncp_linux_bridge_device_worker_1_source,
    nncp_linux_bridge_device_worker_2_destination,
    bridge_device_name,
):
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name=f"linux-{bridge_device_name}-nad",
        interface_name=bridge_device_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def nad_ovs_bridge(
    namespace,
    nncp_ovs_bridge_device_worker_1_source,
    nncp_ovs_bridge_device_worker_2_destination,
    bridge_device_name,
):
    with network_nad(
        namespace=namespace,
        nad_type=OVS_BRIDGE,
        nad_name=f"ovs-{bridge_device_name}-nad",
        interface_name=bridge_device_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def nad_linux_bridge_vlan_1(
    namespace,
    nncp_linux_bridge_device_worker_1_source,
    nncp_linux_bridge_device_worker_2_destination,
    bridge_device_name,
    vlan_id_1,
):
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name=f"linux-{bridge_device_name}-vlan{vlan_id_1}-nad",
        interface_name=bridge_device_name,
        vlan=vlan_id_1,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def nad_ovs_bridge_vlan_1(
    namespace,
    nncp_ovs_bridge_device_worker_1_source,
    nncp_ovs_bridge_device_worker_2_destination,
    bridge_device_name,
    vlan_id_1,
):
    with network_nad(
        namespace=namespace,
        nad_type=OVS_BRIDGE,
        nad_name=f"ovs-{bridge_device_name}-vlan{vlan_id_1}-nad",
        interface_name=bridge_device_name,
        vlan=vlan_id_1,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def nad_linux_bridge_vlan_2(
    namespace,
    nncp_linux_bridge_device_worker_1_source,
    nncp_linux_bridge_device_worker_2_destination,
    bridge_device_name,
    vlan_id_2,
):
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name=f"linux-{bridge_device_name}-vlan{vlan_id_2}-nad",
        interface_name=bridge_device_name,
        vlan=vlan_id_2,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def nad_ovs_bridge_vlan_2(
    namespace,
    nncp_ovs_bridge_device_worker_1_source,
    nncp_ovs_bridge_device_worker_2_destination,
    bridge_device_name,
    vlan_id_2,
):
    with network_nad(
        namespace=namespace,
        nad_type=OVS_BRIDGE,
        nad_name=f"ovs-{bridge_device_name}-vlan{vlan_id_2}-nad",
        interface_name=bridge_device_name,
        vlan=vlan_id_2,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def nad_linux_bridge_vlan_3(
    namespace,
    nncp_linux_bridge_device_worker_1_source,
    nncp_linux_bridge_device_worker_2_destination,
    bridge_device_name,
    vlan_id_3,
):
    with network_nad(
        namespace=namespace,
        nad_type=LINUX_BRIDGE,
        nad_name=f"linux-{bridge_device_name}-vlan{vlan_id_3}-nad",
        interface_name=bridge_device_name,
        vlan=vlan_id_3,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def nad_ovs_bridge_vlan_3(
    namespace,
    nncp_ovs_bridge_device_worker_1_source,
    nncp_ovs_bridge_device_worker_2_destination,
    bridge_device_name,
    vlan_id_3,
):
    with network_nad(
        namespace=namespace,
        nad_type=OVS_BRIDGE,
        nad_name=f"ovs-{bridge_device_name}-vlan{vlan_id_3}-nad",
        interface_name=bridge_device_name,
        vlan=vlan_id_3,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def vm_linux_bridge_attached_vma_source(
    worker_node1,
    namespace,
    unprivileged_client,
    nad_linux_bridge,
    nad_linux_bridge_vlan_1,
    nad_linux_bridge_vlan_2,
    dual_stack_network_data,
):
    network_names = [
        nad_linux_bridge.name,
        nad_linux_bridge_vlan_1.name,
        nad_linux_bridge_vlan_2.name,
    ]

    yield from create_running_vm(
        name=f"vma-{LINUX_BRIDGE}",
        end_ip_octet=1,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        network_names=network_names,
        dual_stack_network_data=dual_stack_network_data,
        client=unprivileged_client,
        namespace=namespace,
    )


@pytest.fixture(scope="class")
def vm_ovs_bridge_attached_vma_source(
    worker_node1,
    namespace,
    unprivileged_client,
    nad_ovs_bridge,
    nad_ovs_bridge_vlan_1,
    nad_ovs_bridge_vlan_2,
    dual_stack_network_data,
):
    network_names = [
        nad_ovs_bridge.name,
        nad_ovs_bridge_vlan_1.name,
        nad_ovs_bridge_vlan_2.name,
    ]

    yield from create_running_vm(
        name=f"vma-{OVS_BRIDGE}",
        end_ip_octet=1,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        network_names=network_names,
        dual_stack_network_data=dual_stack_network_data,
        client=unprivileged_client,
        namespace=namespace,
    )


@pytest.fixture(scope="class")
def vm_linux_bridge_attached_vmb_destination(
    worker_node2,
    namespace,
    unprivileged_client,
    nad_linux_bridge,
    nad_linux_bridge_vlan_1,
    nad_linux_bridge_vlan_3,
    dual_stack_network_data,
):
    network_names = [
        nad_linux_bridge.name,
        nad_linux_bridge_vlan_1.name,
        nad_linux_bridge_vlan_3.name,
    ]

    yield from create_running_vm(
        name=f"vmb-{LINUX_BRIDGE}",
        end_ip_octet=2,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        network_names=network_names,
        dual_stack_network_data=dual_stack_network_data,
        client=unprivileged_client,
        namespace=namespace,
    )


@pytest.fixture(scope="class")
def vm_ovs_bridge_attached_vmb_destination(
    worker_node2,
    namespace,
    unprivileged_client,
    nad_ovs_bridge,
    nad_ovs_bridge_vlan_1,
    nad_ovs_bridge_vlan_3,
    dual_stack_network_data,
):
    network_names = [
        nad_ovs_bridge.name,
        nad_ovs_bridge_vlan_1.name,
        nad_ovs_bridge_vlan_3.name,
    ]

    yield from create_running_vm(
        name=f"vmb-{OVS_BRIDGE}",
        end_ip_octet=2,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        network_names=network_names,
        dual_stack_network_data=dual_stack_network_data,
        client=unprivileged_client,
        namespace=namespace,
    )
