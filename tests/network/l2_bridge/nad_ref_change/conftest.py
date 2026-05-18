import ipaddress
from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

import tests.network.libs.nodenetworkconfigurationpolicy as libnncp
from libs.net.netattachdef import CNIPluginBridgeConfig, NetConfig, NetworkAttachmentDefinition
from libs.net.vmspec import lookup_iface_status
from libs.vm.vm import BaseVirtualMachine
from tests.network.l2_bridge.nad_ref_change.lib_helpers import (
    NET_SEED,
    REF_VM_IFACE_A_HOST_ADDRESS,
    REF_VM_IFACE_B_HOST_ADDRESS,
    REF_VM_NS_VLAN_A,
    REF_VM_NS_VLAN_B,
    UNDER_TEST_VM_2ND_IFACE_HOST_ADDRESS,
    UNDER_TEST_VM_HOST_ADDRESS,
    UNDER_TEST_VM_IFACE_1,
    UNDER_TEST_VM_IFACE_2,
    bridge_vm,
)
from tests.network.libs.connectivity import (
    assert_tcp_connectivity_ns,
    ip_family_predicate,
    secondary_iface_addresses,
)


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
    """Reference VM with one bridge interface on NAD-VLAN-A (ns-vlan-a) and one on NAD-VLAN-B (ns-vlan-b).

    Each secondary interface is isolated in its own Linux network namespace so that frames arriving
    on the wrong VLAN cannot trigger a false TCP response. Namespace setup runs via vm.console()
    after boot so any command failure is immediately visible with the exact error.
    After the setup the guest-agent no longer reports eth1/eth2 IPs; use secondary_iface_addresses()
    directly for all connectivity checks.
    """
    iface_ip_addresses = [
        secondary_iface_addresses(net_seed=NET_SEED, host_address=REF_VM_IFACE_A_HOST_ADDRESS),
        secondary_iface_addresses(net_seed=NET_SEED, host_address=REF_VM_IFACE_B_HOST_ADDRESS),
    ]
    with bridge_vm(
        namespace=namespace.name,
        name="ref-vm-two-vlans",
        client=unprivileged_client,
        nad_names=[bridge_nad_a.name, bridge_nad_b.name],
        ip_addresses=[[], []],
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        console_cmds = [
            "sudo nmcli dev set eth1 managed no",
            "sudo nmcli dev set eth2 managed no",
            f"sudo ip netns add {REF_VM_NS_VLAN_A}",
            f"sudo ip netns add {REF_VM_NS_VLAN_B}",
            f"sudo ip link set eth1 netns {REF_VM_NS_VLAN_A}",
            f"sudo ip link set eth2 netns {REF_VM_NS_VLAN_B}",
        ]
        for addr in iface_ip_addresses[0]:
            console_cmds.append(f"sudo ip netns exec {REF_VM_NS_VLAN_A} ip addr add {addr} dev eth1")
        console_cmds += [
            f"sudo ip netns exec {REF_VM_NS_VLAN_A} ip link set eth1 up",
            f"sudo ip netns exec {REF_VM_NS_VLAN_A} ip link set lo up",
        ]
        for addr in iface_ip_addresses[1]:
            console_cmds.append(f"sudo ip netns exec {REF_VM_NS_VLAN_B} ip addr add {addr} dev eth2")
        console_cmds += [
            f"sudo ip netns exec {REF_VM_NS_VLAN_B} ip link set eth2 up",
            f"sudo ip netns exec {REF_VM_NS_VLAN_B} ip link set lo up",
        ]
        vm.console(commands=console_cmds, timeout=30)
        yield vm


@pytest.fixture(scope="class")
def under_test_vm_two_ifaces(
    namespace: Namespace,
    unprivileged_client: DynamicClient,
    bridge_nad_a: NetworkAttachmentDefinition,
    bridge_nad_b: NetworkAttachmentDefinition,
    ref_vm: BaseVirtualMachine,
) -> Generator[BaseVirtualMachine]:
    iface_a_ips = secondary_iface_addresses(net_seed=NET_SEED, host_address=UNDER_TEST_VM_HOST_ADDRESS)
    iface_b_ips = secondary_iface_addresses(net_seed=NET_SEED, host_address=UNDER_TEST_VM_2ND_IFACE_HOST_ADDRESS)
    with bridge_vm(
        namespace=namespace.name,
        name="under-test-vm-two-ifaces",
        client=unprivileged_client,
        nad_names=[bridge_nad_a.name, bridge_nad_a.name],
        ip_addresses=[iface_a_ips, iface_b_ips],
        iface_names=[UNDER_TEST_VM_IFACE_1, UNDER_TEST_VM_IFACE_2],
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        vm.console(
            commands=[
                "sudo sysctl -w net.ipv4.conf.all.arp_ignore=1",
                "sudo sysctl -w net.ipv4.conf.eth1.arp_ignore=1",
                "sudo sysctl -w net.ipv4.conf.eth2.arp_ignore=1",
                "sudo sysctl -w net.ipv4.conf.all.arp_announce=2",
                "sudo sysctl -w net.ipv4.conf.eth1.arp_announce=2",
                "sudo sysctl -w net.ipv4.conf.eth2.arp_announce=2",
            ],
            timeout=10,
        )
        lookup_iface_status(vm=vm, iface_name=UNDER_TEST_VM_IFACE_1, predicate=ip_family_predicate(iface_a_ips))
        for addr in secondary_iface_addresses(net_seed=NET_SEED, host_address=REF_VM_IFACE_A_HOST_ADDRESS):
            assert_tcp_connectivity_ns(
                client_vm=vm,
                server_vm=ref_vm,
                server_ip=str(ipaddress.ip_interface(addr).ip),
                server_netns=REF_VM_NS_VLAN_A,
            )
        for addr in secondary_iface_addresses(net_seed=NET_SEED, host_address=REF_VM_IFACE_B_HOST_ADDRESS):
            assert_tcp_connectivity_ns(
                client_vm=vm,
                server_vm=ref_vm,
                server_ip=str(ipaddress.ip_interface(addr).ip),
                server_netns=REF_VM_NS_VLAN_B,
                connection_present=False,
            )
        yield vm


@pytest.fixture()
def under_test_vm_iface1_arp_flush(
    under_test_vm_two_ifaces: BaseVirtualMachine,
    ref_vm: BaseVirtualMachine,
) -> Generator[None]:
    # Remove eth2's route so the kernel cannot route via eth2 (VLAN-A) when
    # the iperf3 client is bound to eth1's IP. Without this, ECMP between
    # eth1 (VLAN-B) and eth2 (VLAN-A) allows traffic to reach VLAN-A.
    del_cmds = ["sudo nmcli dev set eth2 managed no"]
    add_cmds = ["sudo nmcli dev set eth2 managed yes"]
    for addr in secondary_iface_addresses(net_seed=NET_SEED, host_address=UNDER_TEST_VM_2ND_IFACE_HOST_ADDRESS):
        ip = ipaddress.ip_interface(address=addr)
        prefix = "-6" if ip.version == 6 else ""
        del_cmds.append(f"sudo ip {prefix} route del {ip.network} dev eth2")
        add_cmds.append(f"sudo ip {prefix} route replace {ip.network} dev eth2")
    del_cmds.append("sudo ip neigh flush dev eth1")
    under_test_vm_two_ifaces.console(commands=del_cmds, timeout=10)
    ref_vm.console(
        commands=[
            f"sudo ip netns exec {REF_VM_NS_VLAN_A} ip neigh flush dev eth1",
            f"sudo ip netns exec {REF_VM_NS_VLAN_B} ip neigh flush dev eth2",
        ],
        timeout=10,
    )
    yield
    under_test_vm_two_ifaces.console(commands=add_cmds, timeout=10)
