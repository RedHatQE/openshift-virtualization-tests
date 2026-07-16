import ipaddress
from collections.abc import Generator
from typing import Final

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.net import nodenetworkconfigurationpolicy as libnncp
from libs.net.ip import random_cidr_addresses_by_family
from libs.net.traffic_generator import TcpServer, VMTcpClient, active_tcp_connections
from libs.net.vmspec import wait_for_ifaces_status
from libs.vm.affinity import new_node_affinity
from libs.vm.oper import run_vms
from libs.vm.spec import Interface, Multus, Network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs import cloudinit
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs.cloudinit import EthernetDevice
from tests.network.libs.localnet import (
    GUEST_2ND_IFACE_NAME,
    LOCALNET_BR_EX_INTERFACE,
    localnet_vm,
)
from utilities.constants.cluster import RHCOS9_WORKER_LABEL

_SERVER_HOST_ADDRESS: Final[int] = 1
_CLIENT_HOST_ADDRESS: Final[int] = 2


@pytest.fixture(scope="class")
def localnet_server_vm(
    unprivileged_client: DynamicClient,
    namespace_localnet_1: Namespace,
    cudn_localnet: libcudn.ClusterUserDefinedNetwork,
    nncp_localnet: libnncp.NodeNetworkConfigurationPolicy,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="server-vm",
        client=unprivileged_client,
        networks=[
            Network(name="default", pod={}),
            Network(name=LOCALNET_BR_EX_INTERFACE, multus=Multus(networkName=cudn_localnet.name)),
        ],
        interfaces=[
            Interface(name="default", masquerade={}),
            Interface(name=LOCALNET_BR_EX_INTERFACE, bridge={}),
        ],
        network_data=cloudinit.NetworkData(
            ethernets={
                GUEST_2ND_IFACE_NAME: EthernetDevice(
                    addresses=random_cidr_addresses_by_family(net_seed=0, host_address=_SERVER_HOST_ADDRESS)
                )
            }
        ),
        affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=True),
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def localnet_client_vm(
    unprivileged_client: DynamicClient,
    namespace_localnet_1: Namespace,
    cudn_localnet: libcudn.ClusterUserDefinedNetwork,
    nncp_localnet: libnncp.NodeNetworkConfigurationPolicy,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="client-vm",
        client=unprivileged_client,
        networks=[
            Network(name="default", pod={}),
            Network(name=LOCALNET_BR_EX_INTERFACE, multus=Multus(networkName=cudn_localnet.name)),
        ],
        interfaces=[
            Interface(name="default", masquerade={}),
            Interface(name=LOCALNET_BR_EX_INTERFACE, bridge={}),
        ],
        network_data=cloudinit.NetworkData(
            ethernets={
                GUEST_2ND_IFACE_NAME: EthernetDevice(
                    addresses=random_cidr_addresses_by_family(net_seed=0, host_address=_CLIENT_HOST_ADDRESS)
                )
            }
        ),
        affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=True),
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def localnet_server_client_running_vms(
    localnet_server_vm: BaseVirtualMachine,
    localnet_client_vm: BaseVirtualMachine,
) -> tuple[BaseVirtualMachine, BaseVirtualMachine]:
    run_vms(vms=(localnet_server_vm, localnet_client_vm))
    for vm in (localnet_server_vm, localnet_client_vm):
        addresses = vm.cloud_init_network_data.ethernets[GUEST_2ND_IFACE_NAME].addresses or []
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                LOCALNET_BR_EX_INTERFACE: [str(ipaddress.ip_interface(addr).ip) for addr in addresses]
            },
        )
    return localnet_server_vm, localnet_client_vm


@pytest.fixture(scope="class")
def localnet_active_tcp_connections(
    localnet_server_client_running_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> Generator[list[tuple[VMTcpClient, TcpServer]]]:
    server_vm, client_vm = localnet_server_client_running_vms
    with active_tcp_connections(
        client_vm=client_vm,
        server_vm=server_vm,
        iface_name=LOCALNET_BR_EX_INTERFACE,
    ) as connections:
        yield connections
