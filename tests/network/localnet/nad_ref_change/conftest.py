from collections.abc import Generator
from typing import Final

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.net.ip import filter_link_local_addresses, random_cidr_addresses_by_family
from libs.net.vmspec import lookup_iface_status, wait_for_ifaces_status
from libs.vm.spec import Interface, Multus, Network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs import cloudinit
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs.connectivity import ARP_ISOLATION_SYSCTL_CMD, poll_tcp_connectivity
from tests.network.localnet.liblocalnet import (
    CUDN_B_NAME,
    GUEST_1ST_IFACE_NAME,
    GUEST_2ND_IFACE_NAME,
    IFACE_A_NAME,
    IFACE_B_NAME,
    LOCALNET_BR_EX_NETWORK,
    LOCALNET_TEST_LABEL,
    localnet_cudn,
    localnet_vm,
)

NET_SEED: Final[int] = 0


@pytest.fixture(scope="module")
def cudn_nad_ref_vlan_b(
    admin_client: DynamicClient,
    cudn_localnet: libcudn.ClusterUserDefinedNetwork,
    vlan_index_number: Generator[int],
) -> Generator[libcudn.ClusterUserDefinedNetwork]:
    with localnet_cudn(
        name=CUDN_B_NAME,
        match_labels=LOCALNET_TEST_LABEL,
        vlan_id=next(vlan_index_number),
        physical_network_name=LOCALNET_BR_EX_NETWORK,
        client=admin_client,
    ) as cudn:
        cudn.wait_for_status_success()
        yield cudn


@pytest.fixture(scope="module")
def ref_vm_localnet(
    namespace_localnet_1: Namespace,
    unprivileged_client: DynamicClient,
    cudn_localnet: libcudn.ClusterUserDefinedNetwork,
    cudn_nad_ref_vlan_b: libcudn.ClusterUserDefinedNetwork,
) -> Generator[BaseVirtualMachine]:
    iface_a_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=1)
    iface_b_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=2)
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="ref-vm",
        client=unprivileged_client,
        networks=[
            Network(name=IFACE_A_NAME, multus=Multus(networkName=cudn_localnet.name)),
            Network(name=IFACE_B_NAME, multus=Multus(networkName=cudn_nad_ref_vlan_b.name)),
        ],
        interfaces=[
            Interface(name=IFACE_A_NAME, bridge={}),
            Interface(name=IFACE_B_NAME, bridge={}),
        ],
        network_data=cloudinit.NetworkData(
            ethernets={
                GUEST_1ST_IFACE_NAME: cloudinit.EthernetDevice(addresses=iface_a_ips),
                GUEST_2ND_IFACE_NAME: cloudinit.EthernetDevice(addresses=iface_b_ips),
            }
        ),
        runcmd=ARP_ISOLATION_SYSCTL_CMD,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                IFACE_A_NAME: [addr.split("/")[0] for addr in iface_a_ips],
                IFACE_B_NAME: [addr.split("/")[0] for addr in iface_b_ips],
            },
        )
        yield vm


@pytest.fixture()
def under_test_vm_localnet(
    namespace_localnet_1: Namespace,
    unprivileged_client: DynamicClient,
    cudn_localnet: libcudn.ClusterUserDefinedNetwork,
) -> Generator[BaseVirtualMachine]:
    iface_a_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=3)
    with localnet_vm(
        namespace=namespace_localnet_1.name,
        name="under-test-vm",
        client=unprivileged_client,
        networks=[Network(name=IFACE_A_NAME, multus=Multus(networkName=cudn_localnet.name))],
        interfaces=[Interface(name=IFACE_A_NAME, bridge={})],
        network_data=cloudinit.NetworkData(
            ethernets={GUEST_1ST_IFACE_NAME: cloudinit.EthernetDevice(addresses=iface_a_ips)},
        ),
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                IFACE_A_NAME: [addr.split("/")[0] for addr in iface_a_ips],
            },
        )
        yield vm


@pytest.fixture()
def baseline_connectivity_localnet(
    under_test_vm_localnet: BaseVirtualMachine,
    ref_vm_localnet: BaseVirtualMachine,
) -> None:
    for server_ip in filter_link_local_addresses(
        ip_addresses=lookup_iface_status(vm=ref_vm_localnet, iface_name=IFACE_A_NAME).ipAddresses
    ):
        poll_tcp_connectivity(
            client_vm=under_test_vm_localnet,
            server_vm=ref_vm_localnet,
            server_ip=str(server_ip),
            server_bind_dev=GUEST_1ST_IFACE_NAME,
        )
    for server_ip in filter_link_local_addresses(
        ip_addresses=lookup_iface_status(vm=ref_vm_localnet, iface_name=IFACE_B_NAME).ipAddresses
    ):
        poll_tcp_connectivity(
            client_vm=under_test_vm_localnet,
            server_vm=ref_vm_localnet,
            server_ip=str(server_ip),
            server_bind_dev=GUEST_2ND_IFACE_NAME,
            expect_connectivity=False,
        )
