from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork

from libs.net.ip import filter_link_local_addresses
from libs.net.traffic_generator import TcpServer, VMTcpClient, client_server_active_connection
from libs.net.udn import UDN_BINDING_DEFAULT_PLUGIN_NAME
from libs.net.vmspec import lookup_iface_status
from libs.vm.affinity import new_node_affinity
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.nodes import RHCOS9_WORKER_LABEL
from tests.network.libs.vm_factory import udn_vm

_UDN_PRIMARY_IFACE_NAME = "udn-primary"


@pytest.fixture(scope="class")
def udn_server_vm(
    admin_client: DynamicClient,
    udn_namespace: Namespace,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
) -> Generator[BaseVirtualMachine]:
    with udn_vm(
        namespace_name=udn_namespace.name,
        name="server-vm",
        client=admin_client,
        binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
        affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=True),
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        lookup_iface_status(
            vm=vm,
            iface_name=_UDN_PRIMARY_IFACE_NAME,
            predicate=lambda iface: (
                "guest-agent" in iface["infoSource"]
                and bool(filter_link_local_addresses(ip_addresses=iface.get("ipAddresses", [])))
            ),
        )
        yield vm


@pytest.fixture(scope="class")
def udn_client_vm(
    admin_client: DynamicClient,
    udn_namespace: Namespace,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
) -> Generator[BaseVirtualMachine]:
    with udn_vm(
        namespace_name=udn_namespace.name,
        name="client-vm",
        client=admin_client,
        binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
        affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=True),
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        lookup_iface_status(
            vm=vm,
            iface_name=_UDN_PRIMARY_IFACE_NAME,
            predicate=lambda iface: (
                "guest-agent" in iface["infoSource"]
                and bool(filter_link_local_addresses(ip_addresses=iface.get("ipAddresses", [])))
            ),
        )
        yield vm


@pytest.fixture(scope="class")
def udn_active_tcp_connection(
    udn_client_vm: BaseVirtualMachine,
    udn_server_vm: BaseVirtualMachine,
) -> Generator[tuple[VMTcpClient, TcpServer]]:
    with client_server_active_connection(
        client_vm=udn_client_vm,
        server_vm=udn_server_vm,
        spec_logical_network=_UDN_PRIMARY_IFACE_NAME,
    ) as connection:
        yield connection
