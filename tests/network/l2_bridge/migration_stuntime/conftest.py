from collections.abc import Generator
from typing import Final

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.net import netattachdef as libnad
from libs.net import nodenetworkconfigurationpolicy as libnncp
from libs.net.ip import random_ipv4_address, random_ipv6_address
from libs.net.vmspec import lookup_iface_status_ip
from libs.vm.affinity import new_pod_affinity
from libs.vm.vm import BaseVirtualMachine
from tests.network.l2_bridge.libl2bridge import secondary_network_vm
from tests.network.libs.stuntime import CLIENT_VM_LABEL, SERVER_VM_LABEL, ContinuousPing

STUNTIME_BRIDGE_IFACE_NAME: Final[str] = "stuntime-bridge"


@pytest.fixture(scope="module")
def l2_bridge_stuntime_nad(
    admin_client: DynamicClient,
    namespace: Namespace,
    bridge_nncp: libnncp.NodeNetworkConfigurationPolicy,
) -> Generator[libnad.NetworkAttachmentDefinition]:
    nad_name = "l2-bridge-nad"
    bridge_name = bridge_nncp.desired_state_spec.interfaces[0].name  # type: ignore[index]
    config = libnad.NetConfig(
        name=nad_name,
        plugins=[
            libnad.CNIPluginBridgeConfig(
                bridge=bridge_name,
                disableContainerInterface=True,
            )
        ],
    )
    with libnad.NetworkAttachmentDefinition(
        name=nad_name,
        namespace=namespace.name,
        config=config,
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def stuntime_server_vm(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    l2_bridge_ip_family: int,
    l2_bridge_stuntime_nad: libnad.NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    with secondary_network_vm(
        namespace=namespace.name,
        name="l2bridge-stuntime-server",
        client=unprivileged_client,
        nad_name=l2_bridge_stuntime_nad.name,
        secondary_iface_name=STUNTIME_BRIDGE_IFACE_NAME,
        secondary_iface_addresses=[
            f"{random_ipv4_address(net_seed=0, host_address=1)}/24",
            f"{random_ipv6_address(net_seed=0, host_address=1)}/64",
        ],
        labels=dict([SERVER_VM_LABEL]),
    ) as server_vm:
        server_vm.start(wait=True)
        server_vm.wait_for_agent_connected()
        yield server_vm


@pytest.fixture(scope="class")
def stuntime_client_vm(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    l2_bridge_stuntime_nad: libnad.NetworkAttachmentDefinition,
    stuntime_server_vm: BaseVirtualMachine,
) -> Generator[BaseVirtualMachine]:
    with secondary_network_vm(
        namespace=namespace.name,
        name="l2bridge-stuntime-client",
        client=unprivileged_client,
        nad_name=l2_bridge_stuntime_nad.name,
        secondary_iface_name=STUNTIME_BRIDGE_IFACE_NAME,
        secondary_iface_addresses=[
            f"{random_ipv4_address(net_seed=0, host_address=2)}/24",
            f"{random_ipv6_address(net_seed=0, host_address=2)}/64",
        ],
        affinity=new_pod_affinity(label=SERVER_VM_LABEL),
        labels=dict([CLIENT_VM_LABEL]),
    ) as client_vm:
        client_vm.start(wait=True)
        client_vm.wait_for_agent_connected()
        yield client_vm


@pytest.fixture(scope="class")
def l2_bridge_ip_family(request: pytest.FixtureRequest) -> int:
    """IP family for stuntime measurement, activated by per-test parametrize."""
    return request.param


@pytest.fixture()
def l2_bridge_active_ping(
    l2_bridge_ip_family: int,
    stuntime_server_vm: BaseVirtualMachine,
    stuntime_client_vm: BaseVirtualMachine,
) -> Generator[ContinuousPing]:
    """Continuous ping session from client to server for stuntime measurement."""
    server_ip = str(
        lookup_iface_status_ip(
            vm=stuntime_server_vm,
            iface_name=STUNTIME_BRIDGE_IFACE_NAME,
            ip_family=l2_bridge_ip_family,
        )
    )

    with ContinuousPing(source_vm=stuntime_client_vm, destination_ip=server_ip) as ping:
        yield ping
