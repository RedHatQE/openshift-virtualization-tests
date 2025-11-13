from collections.abc import Generator

import pytest
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node

import tests.network.libs.nodenetworkconfigurationpolicy as libnncp
from libs.net import netattachdef
from libs.net.traffic_generator import Client, Server
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.ip import random_ipv4_address
from tests.network.localnet.liblocalnet import (
    create_traffic_client,
    create_traffic_server,
    localnet_nad,
    localnet_vm,
    run_vms,
)
from utilities.constants import (
    WORKER_NODE_LABEL_KEY,
)
from utilities.infra import create_ns

LOCALNET_BR_EX_NETWORK = "localnet-br-ex-network"
LOCALNET_OVS_BRIDGE_NETWORK = "localnet-ovs-network"
NNCP_INTERFACE_TYPE_OVS_BRIDGE = "ovs-bridge"


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
def namespace_localnet_1() -> Generator[Namespace]:
    yield from create_ns(name="test-localnet-ns1")  # type: ignore


@pytest.fixture(scope="module")
def namespace_localnet_2() -> Generator[Namespace]:
    yield from create_ns(name="test-localnet-ns2")  # type: ignore


@pytest.fixture(scope="module")
def vlan_id(vlan_index_number: Generator[int]) -> int:
    return next(vlan_index_number)


@pytest.fixture(scope="module")
def nad_localnet_1(
    namespace_localnet_1: Namespace, vlan_id: int
) -> Generator[netattachdef.NetworkAttachmentDefinition]:
    with localnet_nad(
        namespace=namespace_localnet_1.name,
        name="test-localnet-nad1",
        vlan_id=vlan_id,
        network_name=LOCALNET_BR_EX_NETWORK,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def nad_localnet_2(
    namespace_localnet_2: Namespace, vlan_id: int
) -> Generator[netattachdef.NetworkAttachmentDefinition]:
    with localnet_nad(
        namespace=namespace_localnet_2.name,
        name="test-localnet-nad2",
        vlan_id=vlan_id,
        network_name=LOCALNET_BR_EX_NETWORK,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def ipv4_localnet_address_pool() -> Generator[str]:
    return (f"{random_ipv4_address(net_seed=0, host_address=host_value)}/24" for host_value in range(1, 254))


@pytest.fixture(scope="module")
def vm_localnet_1(
    ipv4_localnet_address_pool: Generator[str], nad_localnet_1: netattachdef.NetworkAttachmentDefinition
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=nad_localnet_1.namespace,
        name="test-vm1",
        nad_name=nad_localnet_1.name,
        cidr=next(ipv4_localnet_address_pool),
        spec_logical_network=LOCALNET_BR_EX_NETWORK,
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def vm_localnet_2(
    ipv4_localnet_address_pool: Generator[str], nad_localnet_2: netattachdef.NetworkAttachmentDefinition
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=nad_localnet_2.namespace,
        name="test-vm2",
        nad_name=nad_localnet_2.name,
        cidr=next(ipv4_localnet_address_pool),
        spec_logical_network=LOCALNET_BR_EX_NETWORK,
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def server_client_localnet_vms(
    vm_localnet_1: BaseVirtualMachine, vm_localnet_2: BaseVirtualMachine
) -> Generator[tuple[BaseVirtualMachine, BaseVirtualMachine]]:
    server_vm, client_vm = run_vms(vms=(vm_localnet_1, vm_localnet_2))
    yield (server_vm, client_vm)


@pytest.fixture()
def localnet_server(server_client_localnet_vms: tuple[BaseVirtualMachine, BaseVirtualMachine]) -> Generator[Server]:
    with create_traffic_server(vm=server_client_localnet_vms[0]) as server:
        assert server.is_running()
        yield server


@pytest.fixture()
def localnet_client(server_client_localnet_vms: tuple[BaseVirtualMachine, BaseVirtualMachine]) -> Generator[Client]:
    with create_traffic_client(
        server_vm=server_client_localnet_vms[0],
        client_vm=server_client_localnet_vms[1],
        network_name=LOCALNET_BR_EX_NETWORK,
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
def nad_localnet_ovs_bridge(
    namespace_localnet_1: Namespace,
    vlan_id: int,
) -> Generator[netattachdef.NetworkAttachmentDefinition]:
    with localnet_nad(
        namespace=namespace_localnet_1.name,
        name=LOCALNET_OVS_BRIDGE_NETWORK,
        vlan_id=vlan_id,
        network_name=LOCALNET_OVS_BRIDGE_NETWORK,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def vm_ovs_bridge_localnet_1(
    ipv4_localnet_address_pool: Generator[str],
    nad_localnet_ovs_bridge: netattachdef.NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=nad_localnet_ovs_bridge.namespace,
        name="localnet-ovs-vm1",
        nad_name=nad_localnet_ovs_bridge.name,
        cidr=next(ipv4_localnet_address_pool),
        spec_logical_network=LOCALNET_OVS_BRIDGE_NETWORK,
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def vm_ovs_bridge_localnet_2(
    ipv4_localnet_address_pool: Generator[str],
    nad_localnet_ovs_bridge: netattachdef.NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=nad_localnet_ovs_bridge.namespace,
        name="localnet-ovs-vm2",
        nad_name=nad_localnet_ovs_bridge.name,
        cidr=next(ipv4_localnet_address_pool),
        spec_logical_network=LOCALNET_OVS_BRIDGE_NETWORK,
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def ovs_bridge_server_client_localnet_vms(
    vm_ovs_bridge_localnet_1: BaseVirtualMachine, vm_ovs_bridge_localnet_2: BaseVirtualMachine
) -> Generator[tuple[BaseVirtualMachine, BaseVirtualMachine]]:
    server_vm, client_vm = run_vms(vms=(vm_ovs_bridge_localnet_1, vm_ovs_bridge_localnet_2))
    yield (server_vm, client_vm)


@pytest.fixture()
def localnet_ovs_bridge_server(
    ovs_bridge_server_client_localnet_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> Generator[Server]:
    with create_traffic_server(vm=ovs_bridge_server_client_localnet_vms[0]) as server:
        assert server.is_running()
        yield server


@pytest.fixture()
def localnet_ovs_bridge_client(
    ovs_bridge_server_client_localnet_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> Generator[Client]:
    with create_traffic_client(
        server_vm=ovs_bridge_server_client_localnet_vms[0],
        client_vm=ovs_bridge_server_client_localnet_vms[1],
        network_name=LOCALNET_OVS_BRIDGE_NETWORK,
    ) as client:
        assert client.is_running()
        yield client
