from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

import tests.network.libs.nodenetworkconfigurationpolicy as libnncp
from libs.net.netattachdef import CNIPluginBridgeConfig, NetConfig, NetworkAttachmentDefinition
from libs.net.vmspec import lookup_iface_status
from libs.vm.vm import BaseVirtualMachine
from tests.network.non_functional.ip_persistence.libippersistence import (
    LINUX_BRIDGE_IFACE_NAME,
    linux_bridge_vm,
)
from utilities.constants import LINUX_BRIDGE, WORKER_NODE_LABEL_KEY

IP_PERSISTENCE_BRIDGE_DEVICE_NAME = "br1-test"


@pytest.fixture(scope="module")
def bridge_nncp(
    nmstate_dependent_placeholder: None,
    admin_client: DynamicClient,
    hosts_common_available_ports: list[str],
) -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    with libnncp.NodeNetworkConfigurationPolicy(
        client=admin_client,
        name="ip-persist-bridge",
        desired_state=libnncp.DesiredState(
            interfaces=[
                libnncp.Interface(
                    name=IP_PERSISTENCE_BRIDGE_DEVICE_NAME,
                    type=LINUX_BRIDGE,
                    state=libnncp.Resource.Interface.State.UP,
                    bridge=libnncp.Bridge(
                        port=[libnncp.Port(name=hosts_common_available_ports[-1])],
                    ),
                )
            ]
        ),
        node_selector={WORKER_NODE_LABEL_KEY: ""},
    ) as nncp_br:
        nncp_br.wait_for_status_success()
        yield nncp_br


@pytest.fixture(scope="module")
def bridge_nad(
    admin_client: DynamicClient,
    namespace: Namespace,
    bridge_nncp: Generator[libnncp.NodeNetworkConfigurationPolicy],
) -> Generator[NetworkAttachmentDefinition]:
    config = NetConfig(
        name="test-bridge-network",
        plugins=[CNIPluginBridgeConfig(bridge=IP_PERSISTENCE_BRIDGE_DEVICE_NAME)],
    )
    with NetworkAttachmentDefinition(
        name="test-bridge-network",
        namespace=namespace.name,
        config=config,
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def linux_bridge_vm_for_ip_persist(
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    bridge_nad: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    with linux_bridge_vm(
        namespace=namespace.name,
        name="vm-ip-persist",
        client=unprivileged_client,
        bridge_network_name=bridge_nad.name,
        ipv4_supported_cluster=ipv4_supported_cluster,
        ipv6_supported_cluster=ipv6_supported_cluster,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        #  Wait for IP addresses to be assigned on all interfaces before monitoring begins
        lookup_iface_status(
            vm=vm,
            iface_name="default",
            predicate=lambda iface_status: bool(iface_status.get("ipAddress")),
        )
        lookup_iface_status(
            vm=vm,
            iface_name=LINUX_BRIDGE_IFACE_NAME,
            predicate=lambda iface_status: bool(iface_status.get("ipAddress")),
        )
        yield vm
