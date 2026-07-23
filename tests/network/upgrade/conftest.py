from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from ocp_resources.virtual_machine import VirtualMachine

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.namespace import Namespace

    from libs.vm.vm import BaseVirtualMachine

from libs.net import nodenetworkconfigurationpolicy as libnncp
from libs.net.cluster import cluster_vlans, ipv4_supported_cluster, ipv6_supported_cluster
from libs.net.ip import filter_link_local_addresses, random_ipv4_address, random_ipv6_address
from libs.net.vmspec import lookup_iface_status
from libs.vm.oper import run_vms
from libs.vm.spec import Interface, Multus, Network
from tests.network.libs import cloudinit
from tests.network.libs.localnet import (
    GUEST_1ST_IFACE_NAME,
    LOCALNET_BR_EX_INTERFACE,
    LOCALNET_BR_EX_NETWORK,
    LOCALNET_TEST_LABEL,
    LOCALNET_VM_ANTI_AFFINITY,
    ip_addresses_from_pool,
    localnet_cudn,
    localnet_vm,
)
from tests.network.upgrade.libupgrade import KMP_DISABLED_LABEL
from utilities.constants.cluster import WORKER_NODE_LABEL_KEY
from utilities.constants.networking import KMP_VM_ASSIGNMENT_LABEL, LINUX_BRIDGE
from utilities.constants.virt import ES_NONE
from utilities.infra import create_ns, get_node_selector_dict
from utilities.network import cloud_init, network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body

NAD_MAC_SPOOF_NAME = "brspoofupgrade"


@pytest.fixture(scope="session")
def upgrade_linux_macspoof_nad(
    admin_client,
    upgrade_namespace_scope_session,
):
    with network_nad(
        namespace=upgrade_namespace_scope_session,
        nad_type=LINUX_BRIDGE,
        nad_name=NAD_MAC_SPOOF_NAME,
        interface_name=NAD_MAC_SPOOF_NAME,
        macspoofchk=True,
        add_resource_name=False,
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="session")
def vm_nad_networks_data(upgrade_linux_macspoof_nad):
    return {upgrade_linux_macspoof_nad.name: upgrade_linux_macspoof_nad.name}


@pytest.fixture(scope="session")
def vma_upgrade_mac_spoof(worker_node1, unprivileged_client, upgrade_linux_macspoof_nad, vm_nad_networks_data):
    name = "vma-macspoof"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_linux_macspoof_nad.namespace,
        networks=vm_nad_networks_data,
        interfaces=sorted(vm_nad_networks_data.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address=random_ipv4_address(net_seed=0, host_address=1)),
        body=fedora_vm_body(name=name),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        eviction_strategy=ES_NONE,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def vmb_upgrade_mac_spoof(worker_node1, unprivileged_client, upgrade_linux_macspoof_nad, vm_nad_networks_data):
    name = "vmb-macspoof"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_linux_macspoof_nad.namespace,
        networks=vm_nad_networks_data,
        interfaces=sorted(vm_nad_networks_data.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address=random_ipv4_address(net_seed=0, host_address=2)),
        body=fedora_vm_body(name=name),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        eviction_strategy=ES_NONE,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def running_vma_upgrade_mac_spoof(vma_upgrade_mac_spoof):
    vma_upgrade_mac_spoof.wait_for_ready_status(status=True)
    vma_upgrade_mac_spoof.wait_for_agent_connected()
    return vma_upgrade_mac_spoof


@pytest.fixture(scope="session")
def running_vmb_upgrade_mac_spoof(vmb_upgrade_mac_spoof):
    vmb_upgrade_mac_spoof.wait_for_ready_status(status=True)
    vmb_upgrade_mac_spoof.wait_for_agent_connected()
    return vmb_upgrade_mac_spoof


@pytest.fixture(scope="session")
def namespace_with_disabled_kmp(admin_client):
    yield from create_ns(
        admin_client=admin_client,
        name="kmp-disabled-ns",
        labels={KMP_VM_ASSIGNMENT_LABEL: KMP_DISABLED_LABEL},
    )


@pytest.fixture(scope="session")
def running_vm_with_bridge(
    unprivileged_client,
    upgrade_namespace_scope_session,
    upgrade_br1test_nad,
):
    name = "vm-bridge-connected"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_namespace_scope_session.name,
        networks={upgrade_br1test_nad.name: upgrade_br1test_nad.name},
        interfaces=[upgrade_br1test_nad.name],
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        eviction_strategy=ES_NONE,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="session")
def nncp_localnet_upgrade(
    nmstate_dependent_placeholder: None,
    admin_client: DynamicClient,
) -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    desired_state = libnncp.DesiredState(
        ovn=libnncp.OVN([
            libnncp.BridgeMappings(
                localnet=LOCALNET_BR_EX_NETWORK,
                bridge=libnncp.DEFAULT_OVN_EXTERNAL_BRIDGE,
                state=libnncp.BridgeMappings.State.PRESENT.value,
            )
        ])
    )
    with libnncp.NodeNetworkConfigurationPolicy(
        client=admin_client,
        name="upgrade-localnet-nncp",
        desired_state=desired_state,
        node_selector={WORKER_NODE_LABEL_KEY: ""},
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp


@pytest.fixture(scope="session")
def namespace_localnet_upgrade(
    admin_client: DynamicClient,
    unprivileged_client: DynamicClient,
) -> Generator[Namespace]:
    yield from create_ns(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        name="upgrade-localnet-ns",
        labels=LOCALNET_TEST_LABEL,
    )


@pytest.fixture(scope="session")
def cudn_localnet_upgrade(
    admin_client: DynamicClient,
    nncp_localnet_upgrade: libnncp.NodeNetworkConfigurationPolicy,
    namespace_localnet_upgrade: Namespace,
) -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    with localnet_cudn(
        name=LOCALNET_BR_EX_NETWORK,
        match_labels=LOCALNET_TEST_LABEL,
        vlan_id=cluster_vlans()[0],
        physical_network_name=LOCALNET_BR_EX_NETWORK,
        client=admin_client,
    ) as cudn:
        cudn.wait_for_status_success()
        yield cudn


@pytest.fixture(scope="session")
def ipv4_localnet_address_pool_upgrade() -> Generator[str]:
    return (f"{random_ipv4_address(net_seed=0, host_address=host)}/24" for host in range(1, 254))


@pytest.fixture(scope="session")
def ipv6_localnet_address_pool_upgrade() -> Generator[str]:
    return (f"{random_ipv6_address(net_seed=0, host_address=host)}/64" for host in range(1, 254))


@pytest.fixture(scope="session")
def vm_localnet_upgrade_a(
    unprivileged_client: DynamicClient,
    namespace_localnet_upgrade: Namespace,
    cudn_localnet_upgrade,
    ipv4_localnet_address_pool_upgrade: Generator[str],
    ipv6_localnet_address_pool_upgrade: Generator[str],
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_upgrade.name,
        name="upgrade-localnet-vm-a",
        client=unprivileged_client,
        networks=[Network(name=LOCALNET_BR_EX_INTERFACE, multus=Multus(networkName=cudn_localnet_upgrade.name))],
        interfaces=[Interface(name=LOCALNET_BR_EX_INTERFACE, bridge={})],
        network_data=cloudinit.NetworkData(
            ethernets={
                GUEST_1ST_IFACE_NAME: cloudinit.EthernetDevice(
                    addresses=ip_addresses_from_pool(
                        ipv4_pool=ipv4_localnet_address_pool_upgrade,
                        ipv6_pool=ipv6_localnet_address_pool_upgrade,
                    ),
                ),
            }
        ),
        affinity=LOCALNET_VM_ANTI_AFFINITY,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def vm_localnet_upgrade_b(
    unprivileged_client: DynamicClient,
    namespace_localnet_upgrade: Namespace,
    cudn_localnet_upgrade,
    ipv4_localnet_address_pool_upgrade: Generator[str],
    ipv6_localnet_address_pool_upgrade: Generator[str],
) -> Generator[BaseVirtualMachine]:
    with localnet_vm(
        namespace=namespace_localnet_upgrade.name,
        name="upgrade-localnet-vm-b",
        client=unprivileged_client,
        networks=[Network(name=LOCALNET_BR_EX_INTERFACE, multus=Multus(networkName=cudn_localnet_upgrade.name))],
        interfaces=[Interface(name=LOCALNET_BR_EX_INTERFACE, bridge={})],
        network_data=cloudinit.NetworkData(
            ethernets={
                GUEST_1ST_IFACE_NAME: cloudinit.EthernetDevice(
                    addresses=ip_addresses_from_pool(
                        ipv4_pool=ipv4_localnet_address_pool_upgrade,
                        ipv6_pool=ipv6_localnet_address_pool_upgrade,
                    ),
                ),
            }
        ),
        affinity=LOCALNET_VM_ANTI_AFFINITY,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def localnet_running_vms_upgrade(
    vm_localnet_upgrade_a: BaseVirtualMachine,
    vm_localnet_upgrade_b: BaseVirtualMachine,
) -> tuple[BaseVirtualMachine, BaseVirtualMachine]:
    vm_a, vm_b = run_vms(vms=(vm_localnet_upgrade_a, vm_localnet_upgrade_b))
    ip_families = [
        ip_family for ip_family, enabled in ((4, ipv4_supported_cluster()), (6, ipv6_supported_cluster())) if enabled
    ]
    for vm in (vm_a, vm_b):
        lookup_iface_status(
            vm=vm,
            iface_name=LOCALNET_BR_EX_INTERFACE,
            predicate=lambda interface: (
                len(filter_link_local_addresses(ip_addresses=interface.get("ipAddresses", []))) == len(ip_families)
            ),
        )
    return vm_a, vm_b
