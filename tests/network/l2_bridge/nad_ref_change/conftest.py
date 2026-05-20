from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

import tests.network.libs.nodenetworkconfigurationpolicy as libnncp
from libs.net.ip import filter_link_local_addresses, random_cidr_addresses_by_family
from libs.net.netattachdef import CNIPluginBridgeConfig, NetConfig, NetworkAttachmentDefinition
from libs.net.vmspec import lookup_iface_status, wait_for_ifaces_status
from libs.vm.vm import BaseVirtualMachine
from tests.network.l2_bridge.libl2bridge import MULTI_IFACE_ARP_RUNCMD
from tests.network.l2_bridge.nad_ref_change.lib_helpers import (
    GUEST_IFACE_1,
    GUEST_IFACE_2,
    NET_SEED,
    VM_IFACE_1,
    VM_IFACE_2,
    bridge_vm,
)
from tests.network.libs.connectivity import poll_tcp_connectivity
from utilities.constants import Images
from utilities.storage import get_default_storage_class


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


@pytest.fixture(scope="module")
def ref_vm(
    namespace: Namespace,
    unprivileged_client: DynamicClient,
    bridge_nad_a: NetworkAttachmentDefinition,
    bridge_nad_b: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    iface_a_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=1)
    iface_b_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=2)
    with bridge_vm(
        namespace=namespace.name,
        name="ref-vm",
        client=unprivileged_client,
        nad_names=[bridge_nad_a.name, bridge_nad_b.name],
        ip_addresses=[iface_a_ips, iface_b_ips],
        iface_names=[VM_IFACE_1, VM_IFACE_2],
        runcmd=MULTI_IFACE_ARP_RUNCMD,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                VM_IFACE_1: [addr.split("/")[0] for addr in iface_a_ips],
                VM_IFACE_2: [addr.split("/")[0] for addr in iface_b_ips],
            },
        )
        yield vm


@pytest.fixture(scope="class")
def under_test_vm_two_ifaces(
    namespace: Namespace,
    unprivileged_client: DynamicClient,
    bridge_nad_a: NetworkAttachmentDefinition,
    bridge_nad_b: NetworkAttachmentDefinition,
    ref_vm: BaseVirtualMachine,
) -> Generator[BaseVirtualMachine]:
    iface_a_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=3)
    iface_b_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=4)
    with bridge_vm(
        namespace=namespace.name,
        name="under-test-vm-two-ifaces",
        client=unprivileged_client,
        nad_names=[bridge_nad_a.name, bridge_nad_a.name],
        ip_addresses=[iface_a_ips, iface_b_ips],
        iface_names=[VM_IFACE_1, VM_IFACE_2],
        runcmd=MULTI_IFACE_ARP_RUNCMD,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                VM_IFACE_1: [addr.split("/")[0] for addr in iface_a_ips],
                VM_IFACE_2: [addr.split("/")[0] for addr in iface_b_ips],
            },
        )
        for ip in filter_link_local_addresses(
            ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=VM_IFACE_1).ipAddresses
        ):
            poll_tcp_connectivity(
                client_vm=vm,
                server_vm=ref_vm,
                server_ip=str(ip),
                server_bind_dev=GUEST_IFACE_1,
            )
        for ip in filter_link_local_addresses(
            ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=VM_IFACE_2).ipAddresses
        ):
            poll_tcp_connectivity(
                client_vm=vm,
                server_vm=ref_vm,
                server_ip=str(ip),
                server_bind_dev=GUEST_IFACE_2,
                expect_connectivity=False,
            )
        yield vm


@pytest.fixture()
def non_migratable_under_test_vm(
    admin_client: DynamicClient,
    namespace: Namespace,
    unprivileged_client: DynamicClient,
    bridge_nad_a: NetworkAttachmentDefinition,
    bridge_nad_b: NetworkAttachmentDefinition,
    ref_vm: BaseVirtualMachine,
) -> Generator[BaseVirtualMachine]:
    dv_name = "non-migratable-dv"
    sc = get_default_storage_class(client=admin_client)
    dv_template = {
        "metadata": {"name": dv_name},
        "spec": {
            "storage": {
                "accessModes": ["ReadWriteOnce"],
                "storageClassName": sc.name,
                "resources": {"requests": {"storage": "20Gi"}},
            },
            "source": {
                "registry": {"url": f"docker://{Images.Fedora.FEDORA_CONTAINER_IMAGE}"},
            },
        },
    }
    iface_a_ips = random_cidr_addresses_by_family(net_seed=NET_SEED, host_address=3)
    with bridge_vm(
        namespace=namespace.name,
        name="non-migratable-under-test-vm",
        client=unprivileged_client,
        nad_names=[bridge_nad_a.name],
        ip_addresses=[iface_a_ips],
        iface_names=[VM_IFACE_1],
        rwo_dv_name=dv_name,
        data_volume_template=dv_template,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                VM_IFACE_1: [addr.split("/")[0] for addr in iface_a_ips],
            },
        )
        for ip in filter_link_local_addresses(
            ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=VM_IFACE_1).ipAddresses
        ):
            poll_tcp_connectivity(
                client_vm=vm,
                server_vm=ref_vm,
                server_ip=str(ip),
                server_bind_dev=GUEST_IFACE_1,
            )
        for ip in filter_link_local_addresses(
            ip_addresses=lookup_iface_status(vm=ref_vm, iface_name=VM_IFACE_2).ipAddresses
        ):
            poll_tcp_connectivity(
                client_vm=vm,
                server_vm=ref_vm,
                server_ip=str(ip),
                server_bind_dev=GUEST_IFACE_2,
                expect_connectivity=False,
            )
        yield vm
