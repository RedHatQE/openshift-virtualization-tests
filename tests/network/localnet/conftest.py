from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node

import tests.network.libs.nodenetworkconfigurationpolicy as libnncp
from libs.net.traffic_generator import TcpServer
from libs.net.traffic_generator import VMTcpClient as TcpClient
from libs.net.vmspec import lookup_iface_status
from libs.vm.spec import Interface, Multus, Network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs import cloudinit
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs.ip import random_ipv4_address
from tests.network.localnet.liblocalnet import (
    LINK_STATE_DOWN,
    LOCALNET_BR_EX_INTERFACE,
    LOCALNET_BR_EX_INTERFACE_NO_VLAN,
    LOCALNET_BR_EX_NETWORK,
    LOCALNET_BR_EX_NETWORK_NO_VLAN,
    LOCALNET_OVS_BRIDGE_INTERFACE,
    LOCALNET_OVS_BRIDGE_NETWORK,
    LOCALNET_TEST_LABEL,
    client_server_active_connection,
    create_traffic_client,
    create_traffic_server,
    localnet_cudn,
    localnet_vm,
    run_vms,
)
from utilities.constants import (
    WORKER_NODE_LABEL_KEY,
)
from utilities.infra import create_ns
from utilities.virt import migrate_vm_and_verify

NNCP_INTERFACE_TYPE_OVS_BRIDGE = "ovs-bridge"
PRIMARY_INTERFACE_NAME = "eth0"


@pytest.fixture(scope="module")
def nncp_localnet() -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    desired_state = libnncp.DesiredState(
        ovn=libnncp.OVN([
            libnncp.BridgeMappings(
                localnet=LOCALNET_BR_EX_NETWORK,
                bridge=libnncp.DEFAULT_OVN_EXTERNAL_BRIDGE,
                state=libnncp.BridgeMappings.State.PRESENT.value,
            )
        ])
    )

    with libnncp.NodeNetworkConfigurationPolicy(
        name="test-localnet-nncp",
        desired_state=desired_state,
        node_selector={WORKER_NODE_LABEL_KEY: ""},
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp


@pytest.fixture(scope="module")
def namespace_localnet_1(admin_client: DynamicClient, unprivileged_client: DynamicClient) -> Generator[Namespace]:
    yield from create_ns(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        name="test-localnet-ns1",
        labels=LOCALNET_TEST_LABEL,
    )


@pytest.fixture(scope="module")
def namespace_localnet_2(admin_client: DynamicClient, unprivileged_client: DynamicClient) -> Generator[Namespace]:
    yield from create_ns(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        name="test-localnet-ns2",
        labels=LOCALNET_TEST_LABEL,
    )


@pytest.fixture(scope="module")
def vlan_id(vlan_index_number: Generator[int]) -> int:
    return next(vlan_index_number)


@pytest.fixture(scope="module")
def cudn_localnet(
    vlan_id: int,
    namespace_localnet_1: Namespace,
    namespace_localnet_2: Namespace,
) -> Generator[libcudn.ClusterUserDefinedNetwork]:
    with localnet_cudn(
        name=LOCALNET_BR_EX_NETWORK,
        match_labels=LOCALNET_TEST_LABEL,
        vlan_id=vlan_id,
        physical_network_name=LOCALNET_BR_EX_NETWORK,
    ) as cudn:
        cudn.wait_for_status_success()
        yield cudn


@pytest.fixture(scope="module")
def cudn_localnet_no_vlan(
    namespace_localnet_1: Namespace,
) -> Generator[libcudn.ClusterUserDefinedNetwork]:
    with localnet_cudn(
        name=LOCALNET_BR_EX_NETWORK_NO_VLAN,
        match_labels=LOCALNET_TEST_LABEL,
        physical_network_name=LOCALNET_BR_EX_NETWORK,
    ) as cudn:
        cudn.wait_for_status_success()
        yield cudn


@pytest.fixture(scope="module")
def ipv4_localnet_address_pool() -> Generator[str]:
    return (f"{random_ipv4_address(net_seed=0, host_address=host_value)}/24" for host_value in range(1, 254))


@pytest.fixture(scope="module")
def vm_localnet_1_secondary_ip(ipv4_localnet_address_pool: Generator[str]) -> str:
    return next(ipv4_localnet_address_pool)


@pytest.fixture(scope="module")
def vm_localnet_1(
    namespace_localnet_1: Namespace,
    ipv4_localnet_address_pool: Generator[str],
    vm_localnet_1_secondary_ip: str,
    cudn_localnet: libcudn.ClusterUserDefinedNetwork,
    cudn_localnet_no_vlan: libcudn.ClusterUserDefinedNetwork,
    unprivileged_client: DynamicClient,
) -> Generator[BaseVirtualMachine]:
    """
    Creates a VM with two interfaces:
    - Primary interface (eth0): connected to VLAN-enabled localnet
    - Secondary interface (eth1): connected to no-VLAN localnet
    """
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="test-vm1",
        client=unprivileged_client,
        networks=[
            Network(name=LOCALNET_BR_EX_INTERFACE, multus=Multus(networkName=cudn_localnet.name)),
            Network(name=LOCALNET_BR_EX_INTERFACE_NO_VLAN, multus=Multus(networkName=cudn_localnet_no_vlan.name)),
        ],
        interfaces=[
            Interface(name=LOCALNET_BR_EX_INTERFACE, bridge={}),
            Interface(name=LOCALNET_BR_EX_INTERFACE_NO_VLAN, bridge={}),
        ],
        network_data=cloudinit.NetworkData(
            ethernets={
                PRIMARY_INTERFACE_NAME: cloudinit.EthernetDevice(addresses=[next(ipv4_localnet_address_pool)]),
                "eth1": cloudinit.EthernetDevice(addresses=[vm_localnet_1_secondary_ip]),
            }
        ),
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def vm_localnet_2(
    namespace_localnet_2: Namespace,
    ipv4_localnet_address_pool: Generator[str],
    cudn_localnet: libcudn.ClusterUserDefinedNetwork,
    unprivileged_client: DynamicClient,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_2.name,
        name="test-vm2",
        client=unprivileged_client,
        networks=[Network(name=LOCALNET_BR_EX_INTERFACE, multus=Multus(networkName=cudn_localnet.name))],
        interfaces=[Interface(name=LOCALNET_BR_EX_INTERFACE, bridge={})],
        network_data=cloudinit.NetworkData(
            ethernets={PRIMARY_INTERFACE_NAME: cloudinit.EthernetDevice(addresses=[next(ipv4_localnet_address_pool)])}
        ),
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def localnet_running_vms(
    vm_localnet_1: BaseVirtualMachine, vm_localnet_2: BaseVirtualMachine
) -> tuple[BaseVirtualMachine, BaseVirtualMachine]:
    vm1, vm2 = run_vms(vms=(vm_localnet_1, vm_localnet_2))
    return vm1, vm2


@pytest.fixture()
def localnet_server(localnet_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine]) -> Generator[TcpServer]:
    with create_traffic_server(vm=localnet_running_vms[0]) as server:
        assert server.is_running()
        yield server


@pytest.fixture()
def localnet_client(localnet_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine]) -> Generator[TcpClient]:
    with create_traffic_client(
        server_vm=localnet_running_vms[0],
        client_vm=localnet_running_vms[1],
        spec_logical_network=LOCALNET_BR_EX_INTERFACE,
    ) as client:
        assert client.is_running()
        yield client


@pytest.fixture(scope="module")
def nncp_localnet_on_secondary_node_nic(
    worker_node1: Node, nodes_available_nics: dict[str, list[str]]
) -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    bridge_name = "localnet-ovs-br"
    desired_state = libnncp.DesiredState(
        interfaces=[
            libnncp.Interface(
                name=bridge_name,
                type=NNCP_INTERFACE_TYPE_OVS_BRIDGE,
                ipv4=libnncp.IPv4(enabled=False),
                ipv6=libnncp.IPv6(enabled=False),
                state=libnncp.Resource.Interface.State.UP,
                bridge=libnncp.Bridge(
                    options=libnncp.BridgeOptions(libnncp.STP(enabled=False)),
                    port=[
                        libnncp.Port(
                            name=nodes_available_nics[worker_node1.name][-1],
                        )
                    ],
                ),
            )
        ],
        ovn=libnncp.OVN([
            libnncp.BridgeMappings(
                localnet=LOCALNET_OVS_BRIDGE_NETWORK,
                bridge=bridge_name,
                state=libnncp.BridgeMappings.State.PRESENT.value,
            )
        ]),
    )
    with libnncp.NodeNetworkConfigurationPolicy(
        name=bridge_name,
        desired_state=desired_state,
        node_selector={WORKER_NODE_LABEL_KEY: ""},
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp


@pytest.fixture(scope="module")
def cudn_localnet_ovs_bridge(
    vlan_id: int,
    namespace_localnet_1: Namespace,
) -> Generator[libcudn.ClusterUserDefinedNetwork]:
    with localnet_cudn(
        name=LOCALNET_OVS_BRIDGE_NETWORK,
        match_labels=LOCALNET_TEST_LABEL,
        vlan_id=vlan_id,
        physical_network_name=LOCALNET_OVS_BRIDGE_NETWORK,
    ) as cudn:
        cudn.wait_for_status_success()
        yield cudn


@pytest.fixture(scope="function")
def vm_ovs_bridge_localnet_link_down(
    namespace_localnet_1: Namespace,
    ipv4_localnet_address_pool: Generator[str],
    cudn_localnet_ovs_bridge: libcudn.ClusterUserDefinedNetwork,
    unprivileged_client: DynamicClient,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="localnet-ovs-link-down-vm",
        client=unprivileged_client,
        networks=[
            Network(name=LOCALNET_OVS_BRIDGE_INTERFACE, multus=Multus(networkName=cudn_localnet_ovs_bridge.name))
        ],
        interfaces=[Interface(name=LOCALNET_OVS_BRIDGE_INTERFACE, bridge={}, state=LINK_STATE_DOWN)],
        network_data=cloudinit.NetworkData(
            ethernets={PRIMARY_INTERFACE_NAME: cloudinit.EthernetDevice(addresses=[next(ipv4_localnet_address_pool)])}
        ),
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def vm_ovs_bridge_localnet_1(
    namespace_localnet_1: Namespace,
    ipv4_localnet_address_pool: Generator[str],
    cudn_localnet_ovs_bridge: libcudn.ClusterUserDefinedNetwork,
    unprivileged_client: DynamicClient,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="localnet-ovs-vm1",
        client=unprivileged_client,
        networks=[
            Network(name=LOCALNET_OVS_BRIDGE_INTERFACE, multus=Multus(networkName=cudn_localnet_ovs_bridge.name))
        ],
        interfaces=[Interface(name=LOCALNET_OVS_BRIDGE_INTERFACE, bridge={})],
        network_data=cloudinit.NetworkData(
            ethernets={PRIMARY_INTERFACE_NAME: cloudinit.EthernetDevice(addresses=[next(ipv4_localnet_address_pool)])}
        ),
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def vm_ovs_bridge_localnet_2(
    namespace_localnet_1: Namespace,
    ipv4_localnet_address_pool: Generator[str],
    cudn_localnet_ovs_bridge: libcudn.ClusterUserDefinedNetwork,
    unprivileged_client: DynamicClient,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="localnet-ovs-vm2",
        client=unprivileged_client,
        networks=[
            Network(name=LOCALNET_OVS_BRIDGE_INTERFACE, multus=Multus(networkName=cudn_localnet_ovs_bridge.name))
        ],
        interfaces=[Interface(name=LOCALNET_OVS_BRIDGE_INTERFACE, bridge={})],
        network_data=cloudinit.NetworkData(
            ethernets={PRIMARY_INTERFACE_NAME: cloudinit.EthernetDevice(addresses=[next(ipv4_localnet_address_pool)])}
        ),
    ) as vm:
        yield vm


@pytest.fixture(scope="function")
def ovs_bridge_localnet_running_vms_one_with_interface_down(
    vm_ovs_bridge_localnet_link_down: BaseVirtualMachine, vm_ovs_bridge_localnet_1: BaseVirtualMachine
) -> Generator[tuple[BaseVirtualMachine, BaseVirtualMachine]]:
    vm1, vm2 = run_vms(vms=(vm_ovs_bridge_localnet_link_down, vm_ovs_bridge_localnet_1))
    lookup_iface_status(
        vm=vm_ovs_bridge_localnet_link_down,
        iface_name=LOCALNET_OVS_BRIDGE_INTERFACE,
        predicate=lambda interface: "guest-agent" in interface["infoSource"]
        and interface["linkState"] == LINK_STATE_DOWN,
    )
    yield vm1, vm2


@pytest.fixture(scope="module")
def ovs_bridge_localnet_running_vms(
    vm_ovs_bridge_localnet_1: BaseVirtualMachine, vm_ovs_bridge_localnet_2: BaseVirtualMachine
) -> Generator[tuple[BaseVirtualMachine, BaseVirtualMachine]]:
    vm1, vm2 = run_vms(vms=(vm_ovs_bridge_localnet_1, vm_ovs_bridge_localnet_2))
    yield vm1, vm2


@pytest.fixture()
def localnet_ovs_bridge_server(
    ovs_bridge_localnet_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> Generator[TcpServer]:
    with create_traffic_server(vm=ovs_bridge_localnet_running_vms[0]) as server:
        assert server.is_running()
        yield server


@pytest.fixture()
def localnet_ovs_bridge_client(
    ovs_bridge_localnet_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> Generator[TcpClient]:
    with create_traffic_client(
        server_vm=ovs_bridge_localnet_running_vms[0],
        client_vm=ovs_bridge_localnet_running_vms[1],
        spec_logical_network=LOCALNET_OVS_BRIDGE_INTERFACE,
    ) as client:
        assert client.is_running()
        yield client


@pytest.fixture()
def localnet_vms_have_connectivity(localnet_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine]) -> None:
    with client_server_active_connection(
        client_vm=localnet_running_vms[0],
        server_vm=localnet_running_vms[1],
        spec_logical_network=LOCALNET_BR_EX_INTERFACE,
    ):
        pass


@pytest.fixture()
def migrated_localnet_vm(
    localnet_vms_have_connectivity: None, localnet_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine]
) -> BaseVirtualMachine:
    vm, _ = localnet_running_vms
    migrate_vm_and_verify(vm=vm)
    return vm
