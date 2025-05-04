from collections.abc import Generator

import pytest
from ocp_resources.namespace import Namespace

import tests.network.libs.nodenetworkconfigurationpolicy as libnncp
from libs.net import netattachdef
from libs.net.traffic_generator import Client, Server
from libs.net.vmspec import IP_ADDRESS, lookup_iface_status
from libs.vm.vm import BaseVirtualMachine
from tests.network.localnet.liblocalnet import NETWORK_NAME, localnet_nad, localnet_vm
from utilities.constants import (
    WORKER_NODE_LABEL_KEY,
)
from utilities.infra import create_ns

_IPERF_SERVER_PORT = 5201


@pytest.fixture(scope="module")
def nncp_localnet() -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    desired_state = libnncp.DesiredState(
        ovn=libnncp.OVN([
            libnncp.BridgeMappings(
                localnet=NETWORK_NAME,
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
    with localnet_nad(namespace=namespace_localnet_1.name, name="test-localnet-nad1", vlan_id=vlan_id) as nad:
        yield nad


@pytest.fixture(scope="module")
def nad_localnet_2(
    namespace_localnet_2: Namespace, vlan_id: int
) -> Generator[netattachdef.NetworkAttachmentDefinition]:
    with localnet_nad(namespace=namespace_localnet_2.name, name="test-localnet-nad2", vlan_id=vlan_id) as nad:
        yield nad


@pytest.fixture(scope="module")
def vm_localnet_1(nad_localnet_1: netattachdef.NetworkAttachmentDefinition) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=nad_localnet_1.namespace, name="test-vm1", network=nad_localnet_1.name, cidr="10.0.0.1/24"
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def vm_localnet_2(nad_localnet_2: netattachdef.NetworkAttachmentDefinition) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=nad_localnet_2.namespace, name="test-vm2", network=nad_localnet_2.name, cidr="10.0.0.2/24"
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def vms_localnet(
    vm_localnet_1: BaseVirtualMachine, vm_localnet_2: BaseVirtualMachine
) -> Generator[tuple[BaseVirtualMachine, BaseVirtualMachine]]:
    vms = (vm_localnet_1, vm_localnet_2)
    for vm in vms:
        vm.start()
    for vm in vms:
        vm.wait_for_ready_status(status=True)
        vm.vmi.wait_for_condition(condition=vm.Condition.Type.AGENT_CONNECTED, status=vm.Condition.Status.TRUE)
    yield vms


@pytest.fixture()
def localnet_server(vms_localnet: tuple[BaseVirtualMachine, BaseVirtualMachine]) -> Generator[Server]:
    vm1, _ = vms_localnet
    with Server(vm=vm1, port=_IPERF_SERVER_PORT) as server:
        assert server.is_running()
        yield server


@pytest.fixture()
def localnet_client(vms_localnet: tuple[BaseVirtualMachine, BaseVirtualMachine]) -> Generator[Client]:
    vm1, vm2 = vms_localnet
    with Client(
        vm=vm2,
        server_ip=lookup_iface_status(vm=vm1, iface_name=NETWORK_NAME)[IP_ADDRESS],
        server_port=_IPERF_SERVER_PORT,
    ) as client:
        assert client.is_running()
        yield client
