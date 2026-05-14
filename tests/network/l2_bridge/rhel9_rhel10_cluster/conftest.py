import ipaddress
from collections.abc import Generator
from typing import Final

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.net.ip import random_cidr_addresses_by_family
from libs.net.netattachdef import NetworkAttachmentDefinition
from libs.net.traffic_generator import TcpServer, VMTcpClient, active_tcp_connections
from libs.net.vmspec import wait_for_ifaces_status
from libs.vm.affinity import new_node_affinity
from libs.vm.oper import run_vms
from libs.vm.vm import BaseVirtualMachine
from tests.network.l2_bridge.libl2bridge import RHCOS9_WORKER_LABEL, secondary_network_vm

LINUX_BRIDGE_NETWORK_NAME: Final[str] = "linux-bridge-1"

_SERVER_HOST_ADDRESS: Final[int] = 1
_CLIENT_HOST_ADDRESS: Final[int] = 2


@pytest.fixture(scope="class")
def bridge_active_tcp_connections(
    bridge_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> Generator[list[tuple[VMTcpClient, TcpServer]]]:
    server_vm, client_vm = bridge_running_vms
    with active_tcp_connections(
        client_vm=client_vm,
        server_vm=server_vm,
        iface_name=LINUX_BRIDGE_NETWORK_NAME,
    ) as connections:
        yield connections


@pytest.fixture(scope="class")
def bridge_running_vms(
    bridge_server_vm: BaseVirtualMachine,
    bridge_client_vm: BaseVirtualMachine,
) -> tuple[BaseVirtualMachine, BaseVirtualMachine]:
    run_vms(vms=(bridge_server_vm, bridge_client_vm))
    server_addresses = bridge_server_vm.cloud_init_network_data.ethernets["eth1"].addresses or []
    client_addresses = bridge_client_vm.cloud_init_network_data.ethernets["eth1"].addresses or []
    for vm, addresses in ((bridge_server_vm, server_addresses), (bridge_client_vm, client_addresses)):
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                LINUX_BRIDGE_NETWORK_NAME: [str(ipaddress.ip_interface(addr).ip) for addr in addresses]
            },
        )
    return bridge_server_vm, bridge_client_vm


@pytest.fixture(scope="class")
def bridge_server_vm(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    bridge_nad: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    with secondary_network_vm(
        namespace=namespace.name,
        name="server-vm",
        client=unprivileged_client,
        nad_name=bridge_nad.name,
        secondary_iface_name=LINUX_BRIDGE_NETWORK_NAME,
        secondary_iface_addresses=random_cidr_addresses_by_family(net_seed=0, host_address=_SERVER_HOST_ADDRESS),
        affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=True),
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def bridge_client_vm(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    bridge_nad: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    with secondary_network_vm(
        namespace=namespace.name,
        name="client-vm",
        client=unprivileged_client,
        nad_name=bridge_nad.name,
        secondary_iface_name=LINUX_BRIDGE_NETWORK_NAME,
        secondary_iface_addresses=random_cidr_addresses_by_family(net_seed=0, host_address=_CLIENT_HOST_ADDRESS),
        affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=True),
    ) as vm:
        yield vm
