from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

import tests.network.libs.nodenetworkconfigurationpolicy as libnncp
from libs.net.netattachdef import CNIPluginBridgeConfig, NetConfig, NetworkAttachmentDefinition
from libs.vm.vm import BaseVirtualMachine
from tests.network.l2_bridge.vmi_interfaces_stability.lib_helpers import (
    secondary_network_vm,
    wait_for_stable_ifaces,
)


@pytest.fixture(scope="class")
def running_linux_bridge_vm(
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    bridge_nad: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    with secondary_network_vm(
        namespace=namespace.name,
        name="vm-iface-stability",
        client=unprivileged_client,
        bridge_network_name=bridge_nad.name,
        ipv4_supported_cluster=ipv4_supported_cluster,
        ipv6_supported_cluster=ipv6_supported_cluster,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_stable_ifaces(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def bridge_nad(
    admin_client: DynamicClient,
    namespace: Namespace,
    bridge_nncp: libnncp.NodeNetworkConfigurationPolicy,
) -> Generator[NetworkAttachmentDefinition]:
    config = NetConfig(
        name="test-bridge-network",
        plugins=[CNIPluginBridgeConfig(bridge=bridge_nncp.desired_state_spec.interfaces[0].name)],  # type: ignore
    )
    with NetworkAttachmentDefinition(
        name="test-bridge-network",
        namespace=namespace.name,
        config=config,
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def stable_ips(running_linux_bridge_vm: BaseVirtualMachine) -> dict[str, str]:
    return {iface.name: iface.ipAddress for iface in running_linux_bridge_vm.vmi.interfaces}
