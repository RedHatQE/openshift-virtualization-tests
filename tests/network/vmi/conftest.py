from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition

from libs.net.vmspec import lookup_iface_status
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Interface, Multus, Network
from libs.vm.vm import BaseVirtualMachine
from tests.network.vmi.libippersistence import vm_cloud_init_data
from utilities.constants import LINUX_BRIDGE, WORKER_NODE_LABEL_KEY
from utilities.network import network_device, network_nad


@pytest.fixture(scope="module")
def ip_persistence_bridge_device_name(index_number: Generator[int]) -> str:
    return f"br{next(index_number)}test"


@pytest.fixture(scope="module")
def bridge_devices(
    nmstate_dependent_placeholder: None,
    admin_client: DynamicClient,
    hosts_common_available_ports: list[str],
    ip_persistence_bridge_device_name: str,
) -> Generator:
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="ip-persist-bridge",
        interface_name=ip_persistence_bridge_device_name,
        node_selector_labels={WORKER_NODE_LABEL_KEY: ""},
        ports=[hosts_common_available_ports[-1]],
        client=admin_client,
    ) as br:
        yield br


@pytest.fixture(scope="module")
def bridge_network(
    admin_client: DynamicClient,
    namespace: Namespace,
    bridge_devices,
    ip_persistence_bridge_device_name: str,
) -> Generator[NetworkAttachmentDefinition]:
    with network_nad(
        client=admin_client,
        nad_type=LINUX_BRIDGE,
        nad_name="test-bridge-network",
        interface_name=ip_persistence_bridge_device_name,
        namespace=namespace,
        add_resource_name=False,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def vm_single_nic_with_pod(
    namespace: Namespace,
    unprivileged_client: DynamicClient,
    bridge_network: NetworkAttachmentDefinition,
    ipv4_supported_cluster: bool,
    ipv6_supported_cluster: bool,
) -> Generator[BaseVirtualMachine]:
    spec = base_vmspec()
    spec.template.spec.domain.devices.interfaces = [  # type: ignore
        Interface(name="default", masquerade={}),
        Interface(name="linux-bridge", bridge={}),
    ]
    spec.template.spec.networks = [
        Network(name="default", pod={}),
        Network(name="linux-bridge", multus=Multus(networkName=bridge_network.name)),
    ]

    network_data = vm_cloud_init_data(
        ipv4_supported_cluster=ipv4_supported_cluster,
        ipv6_supported_cluster=ipv6_supported_cluster,
    )

    with fedora_vm(
        namespace=namespace.name,
        name="vm-fedora",
        client=unprivileged_client,
        spec=spec,
    ) as vm:
        vm.add_cloud_init(netdata=network_data)
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        lookup_iface_status(
            vm=vm,
            iface_name="default",
            predicate=lambda iface_status: bool(iface_status.get("ipAddress")),
        )
        lookup_iface_status(
            vm=vm,
            iface_name="linux-bridge",
            predicate=lambda iface_status: bool(iface_status.get("ipAddress")),
        )
        yield vm
