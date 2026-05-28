from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.net.ip import random_cidr_addresses_by_family
from libs.net.netattachdef import CNIPluginBridgeConfig, NetConfig, NetworkAttachmentDefinition
from libs.net.vmspec import wait_for_ifaces_status
from libs.vm.vm import BaseVirtualMachine
from tests.network.l2_bridge.libl2bridge import LINUX_BRIDGE_IFACE_NAME_1, LINUX_BRIDGE_IFACE_NAME_2
from tests.network.l2_bridge.nad_ref_change.lib_helpers import (
    NET_SEED,
    two_secondary_bridge_vm,
)
from tests.network.libs import nodenetworkconfigurationpolicy as libnncp
from tests.network.libs.connectivity import ARP_ISOLATION_SYSCTL_CMD


@pytest.fixture(scope="module")
def bridge_nad_a(
    admin_client: DynamicClient,
    namespace: Namespace,
    bridge_nncp: libnncp.NodeNetworkConfigurationPolicy,
    vlan_index_number: Generator[int],
) -> Generator[NetworkAttachmentDefinition]:
    bridge = bridge_nncp.desired_state_spec.interfaces[0].name  # type: ignore
    with NetworkAttachmentDefinition(
        name="nad-vlan-a",
        namespace=namespace.name,
        config=NetConfig(
            name="nad-vlan-a", plugins=[CNIPluginBridgeConfig(bridge=bridge, vlan=next(vlan_index_number))]
        ),
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def bridge_nad_b(
    admin_client: DynamicClient,
    namespace: Namespace,
    bridge_nncp: libnncp.NodeNetworkConfigurationPolicy,
    vlan_index_number: Generator[int],
) -> Generator[NetworkAttachmentDefinition]:
    bridge = bridge_nncp.desired_state_spec.interfaces[0].name  # type: ignore[union-attr, index]
    with NetworkAttachmentDefinition(
        name="nad-vlan-b",
        namespace=namespace.name,
        config=NetConfig(
            name="nad-vlan-b", plugins=[CNIPluginBridgeConfig(bridge=bridge, vlan=next(vlan_index_number))]
        ),
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def under_test_vm_two_ifaces(
    namespace: Namespace,
    unprivileged_client: DynamicClient,
    bridge_nad_a: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    iface_a_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=3)
    iface_b_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=4)
    with two_secondary_bridge_vm(
        namespace=namespace.name,
        name="under-test-vm-two-ifaces",
        client=unprivileged_client,
        nad_names=[bridge_nad_a.name, bridge_nad_a.name],
        ip_addresses=[iface_a_ips, iface_b_ips],
        iface_names=[LINUX_BRIDGE_IFACE_NAME_1, LINUX_BRIDGE_IFACE_NAME_2],
        runcmd=ARP_ISOLATION_SYSCTL_CMD,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                LINUX_BRIDGE_IFACE_NAME_1: [addr.split("/")[0] for addr in iface_a_ips],
                LINUX_BRIDGE_IFACE_NAME_2: [addr.split("/")[0] for addr in iface_b_ips],
            },
        )
        yield vm
