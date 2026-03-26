from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

import tests.network.libs.nodenetworkconfigurationpolicy as libnncp
from libs.net import netattachdef as libnad
from libs.net.ip import random_ipv4_address
from libs.vm.spec import Interface, Multus, Network
from libs.vm.vm import BaseVirtualMachine
from tests.network.localnet.liblocalnet import (
    LOCALNET_IPAM_INTERFACE,
    LOCALNET_OVS_BRIDGE_NETWORK,
    localnet_vm,
    run_vms,
)


@pytest.fixture()
def localnet_ipam_nad(
    admin_client: DynamicClient,
    nncp_localnet_on_secondary_node_nic: libnncp.NodeNetworkConfigurationPolicy,
    vlan_id: int,
    namespace_localnet_1: Namespace,
) -> Generator[libnad.NetworkAttachmentDefinition]:
    localnet_ipam_nad_name = "localnet-ipam"
    config = libnad.NetConfig(
        name=LOCALNET_OVS_BRIDGE_NETWORK,
        plugins=[
            libnad.CNIPluginOvnK8sConfig(
                topology=libnad.CNIPluginOvnK8sConfig.Topology.LOCALNET.value,
                netAttachDefName=f"{namespace_localnet_1.name}/{localnet_ipam_nad_name}",
                vlanID=vlan_id,
                subnets=f"{random_ipv4_address(net_seed=0, host_address=0)}/24",
            )
        ],
    )

    with libnad.NetworkAttachmentDefinition(
        name=localnet_ipam_nad_name,
        namespace=namespace_localnet_1.name,
        config=config,
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture()
def vm1_localnet_ipam(
    namespace_localnet_1: Namespace,
    localnet_ipam_nad: libnad.NetworkAttachmentDefinition,
    unprivileged_client: DynamicClient,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="vm1-localnet-ipam",
        client=unprivileged_client,
        networks=[
            Network(
                name=LOCALNET_IPAM_INTERFACE,
                multus=Multus(networkName=localnet_ipam_nad.name),
            ),
        ],
        interfaces=[
            Interface(name=LOCALNET_IPAM_INTERFACE, bridge={}),
        ],
    ) as vm:
        yield vm


@pytest.fixture()
def vm2_localnet_ipam(
    namespace_localnet_1: Namespace,
    localnet_ipam_nad: libnad.NetworkAttachmentDefinition,
    unprivileged_client: DynamicClient,
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="vm2-localnet-ipam",
        client=unprivileged_client,
        networks=[
            Network(
                name=LOCALNET_IPAM_INTERFACE,
                multus=Multus(networkName=localnet_ipam_nad.name),
            ),
        ],
        interfaces=[
            Interface(name=LOCALNET_IPAM_INTERFACE, bridge={}),
        ],
    ) as vm:
        yield vm


@pytest.fixture()
def localnet_ipam_running_vms(
    vm1_localnet_ipam: BaseVirtualMachine, vm2_localnet_ipam: BaseVirtualMachine
) -> tuple[BaseVirtualMachine, BaseVirtualMachine]:
    vm1, vm2 = run_vms(vms=(vm1_localnet_ipam, vm2_localnet_ipam))
    return vm1, vm2
