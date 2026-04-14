import ipaddress
from collections.abc import Generator
from ipaddress import ip_interface
from typing import Final

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

import tests.network.libs.nodenetworkconfigurationpolicy as libnncp
from libs.net.ip import random_ip_addresses_by_family
from libs.net.netattachdef import (
    CNIPluginBandwidthConfig,
    CNIPluginBridgeConfig,
    NetConfig,
    NetworkAttachmentDefinition,
)
from libs.net.vmspec import wait_for_ifaces_status
from libs.vm.guest import guest_iface_name
from libs.vm.vm import BaseVirtualMachine
from tests.network.l2_bridge.bandwidth.lib_helpers import (
    BANDWIDTH_RATE_BPS,
    BANDWIDTH_SECONDARY_IFACE_NAME,
    secondary_network_vm,
)

_NAD_NAME: Final[str] = "br-bw-test-nad"


@pytest.fixture(scope="module")
def bandwidth_nad(
    admin_client: DynamicClient,
    namespace: Namespace,
    bridge_nncp: libnncp.NodeNetworkConfigurationPolicy,
) -> Generator[NetworkAttachmentDefinition]:
    config = NetConfig(
        name=_NAD_NAME,
        plugins=[
            CNIPluginBridgeConfig(
                bridge=bridge_nncp.desired_state_spec.interfaces[0].name  # type: ignore
            ),
            CNIPluginBandwidthConfig(
                ingressRate=BANDWIDTH_RATE_BPS,
                ingressBurst=BANDWIDTH_RATE_BPS,
                egressRate=BANDWIDTH_RATE_BPS,
                egressBurst=BANDWIDTH_RATE_BPS,
            ),
        ],
    )
    with NetworkAttachmentDefinition(
        name=_NAD_NAME,
        namespace=namespace.name,
        config=config,
        client=admin_client,
    ) as bw_nad:
        yield bw_nad


@pytest.fixture(scope="module")
def server_vm(
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    bandwidth_nad: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    addresses = [
        f"{ip}/64" if ipaddress.ip_address(ip).version == 6 else f"{ip}/24"
        for ip in random_ip_addresses_by_family(
            ipv4_supported=ipv4_supported_cluster,
            ipv6_supported=ipv6_supported_cluster,
            net_seed=0,
            host_address=1,
        )
    ]
    with secondary_network_vm(
        namespace=namespace.name,
        name="bw-server-vm",
        client=unprivileged_client,
        nad_name=bandwidth_nad.name,
        secondary_iface_name=BANDWIDTH_SECONDARY_IFACE_NAME,
        secondary_iface_addresses=addresses,
        ipv4_supported=ipv4_supported_cluster,
        ipv6_supported=ipv6_supported_cluster,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                BANDWIDTH_SECONDARY_IFACE_NAME: [
                    str(ip_interface(addr).ip)
                    for addr in vm.cloud_init_network_data.ethernets[guest_iface_name(ordinal=2)].addresses
                ]
            },
        )
        yield vm


@pytest.fixture(scope="module")
def client_vm(
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    bandwidth_nad: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    addresses = [
        f"{ip}/64" if ipaddress.ip_address(ip).version == 6 else f"{ip}/24"
        for ip in random_ip_addresses_by_family(
            ipv4_supported=ipv4_supported_cluster,
            ipv6_supported=ipv6_supported_cluster,
            net_seed=0,
            host_address=2,
        )
    ]
    with secondary_network_vm(
        namespace=namespace.name,
        name="bw-client-vm",
        client=unprivileged_client,
        nad_name=bandwidth_nad.name,
        secondary_iface_name=BANDWIDTH_SECONDARY_IFACE_NAME,
        secondary_iface_addresses=addresses,
        ipv4_supported=ipv4_supported_cluster,
        ipv6_supported=ipv6_supported_cluster,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                BANDWIDTH_SECONDARY_IFACE_NAME: [
                    str(ip_interface(addr).ip)
                    for addr in vm.cloud_init_network_data.ethernets[guest_iface_name(ordinal=2)].addresses
                ]
            },
        )
        yield vm
