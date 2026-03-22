import logging
from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.net.vmspec import lookup_iface_status_ip
from libs.vm.spec import Interface, Multus, Network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs import cloudinit
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.localnet.liblocalnet import (
    GUEST_1ST_IFACE_NAME,
    LOCALNET_OVS_BRIDGE_INTERFACE,
    ip_addresses_from_pool,
    libnncp,
    localnet_vm,
)
from tests.network.localnet.migration_stuntime import libstuntime
from utilities.infra import get_node_selector_dict

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def localnet_stuntime_server_vm(
    unprivileged_client: DynamicClient,
    nncp_localnet_on_secondary_node_nic: libnncp.NodeNetworkConfigurationPolicy,
    cudn_localnet_ovs_bridge: libcudn.ClusterUserDefinedNetwork,
    namespace_localnet_1: Namespace,
    ipv4_localnet_address_pool: Generator[str],
    ipv6_localnet_address_pool: Generator[str],
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="localnet-stuntime-server",
        client=unprivileged_client,
        networks=[
            Network(name=LOCALNET_OVS_BRIDGE_INTERFACE, multus=Multus(networkName=cudn_localnet_ovs_bridge.name))
        ],
        interfaces=[Interface(name=LOCALNET_OVS_BRIDGE_INTERFACE, bridge={})],
        network_data=cloudinit.NetworkData(
            ethernets={
                GUEST_1ST_IFACE_NAME: cloudinit.EthernetDevice(
                    addresses=ip_addresses_from_pool(
                        ipv4_pool=ipv4_localnet_address_pool,
                        ipv6_pool=ipv6_localnet_address_pool,
                    )
                )
            }
        ),
        pod_anti_affinity=False,
    ) as server_vm:
        server_vm.start(wait=True)
        server_vm.wait_for_agent_connected()
        yield server_vm


@pytest.fixture(scope="class")
def localnet_stuntime_client_vm(
    unprivileged_client: DynamicClient,
    cudn_localnet_ovs_bridge: libcudn.ClusterUserDefinedNetwork,
    namespace_localnet_1: Namespace,
    ipv4_localnet_address_pool: Generator[str],
    ipv6_localnet_address_pool: Generator[str],
    localnet_stuntime_server_vm: BaseVirtualMachine,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="localnet-stuntime-client",
        client=unprivileged_client,
        networks=[
            Network(name=LOCALNET_OVS_BRIDGE_INTERFACE, multus=Multus(networkName=cudn_localnet_ovs_bridge.name))
        ],
        interfaces=[Interface(name=LOCALNET_OVS_BRIDGE_INTERFACE, bridge={})],
        network_data=cloudinit.NetworkData(
            ethernets={
                GUEST_1ST_IFACE_NAME: cloudinit.EthernetDevice(
                    addresses=ip_addresses_from_pool(
                        ipv4_pool=ipv4_localnet_address_pool,
                        ipv6_pool=ipv6_localnet_address_pool,
                    )
                )
            }
        ),
        pod_anti_affinity=False,
        node_selector=get_node_selector_dict(node_selector=localnet_stuntime_server_vm.vmi.node.name),
    ) as client_vm:
        client_vm.start(wait=True)
        client_vm.wait_for_agent_connected()
        # Clear node selector to allow migration to any node
        client_vm.update_template_node_selector(node_selector=None)
        yield client_vm


@pytest.fixture()
def active_ping(
    request: pytest.FixtureRequest,
    localnet_stuntime_server_vm: BaseVirtualMachine,
    localnet_stuntime_client_vm: BaseVirtualMachine,
) -> Generator[libstuntime.ContinuousPing]:
    """Continuous ping session from client to server for stuntime measurement."""
    ip_family = request.param
    server_ip = str(
        lookup_iface_status_ip(
            vm=localnet_stuntime_server_vm,
            iface_name=LOCALNET_OVS_BRIDGE_INTERFACE,
            ip_family=ip_family,
        )
    )

    with libstuntime.ContinuousPing(source_vm=localnet_stuntime_client_vm, destination_ip=server_ip) as ping:
        yield ping
