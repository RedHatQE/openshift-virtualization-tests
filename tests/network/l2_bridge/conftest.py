# -*- coding: utf-8 -*-
import contextlib
import shlex
from ipaddress import ip_interface

import pytest
from pyhelper_utils.shell import run_ssh_commands

from tests.network.libs.dhcpd import (
    DHCP_IP_RANGE_END,
    DHCP_IP_RANGE_START,
    DHCP_IP_SUBNET,
    DHCP_SERVER_CONF_FILE,
    DHCP_SERVICE_RESTART,
    verify_dhcpd_activated,
)
from tests.network.libs.ip import random_ipv4_address
from tests.network.utils import update_cloud_init_extra_user_data
from utilities.infra import get_node_selector_dict, name_prefix
from utilities.network import (
    cloud_init_network_data,
    get_vmi_mac_address_by_iface_name,
    network_device,
    network_nad,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    prepare_cloud_init_user_data,
)

#: Test setup example (third octet is random)
#       .........                                                                                    ..........
#       |       |---eth1:172.16.0.1                                                172.16.0.2:eth1---|        |
#       | VM-A  |---eth2:172.16.2.1    : multicast(ICMP), custom eth type test:    172.16.2.2:eth2---|  VM-B  |
#       |       |---eth3:172.16.3.1    : DHCP test :                               172.16.3.2:eth3---|        |
#       |.......|---eth4:172.16.4.1    : mpls test :                               172.16.4.2:eth4---|........|


VMA_MPLS_LOOPBACK_IP = f"{random_ipv4_address(net_seed=5, host_address=1)}/32"
VMA_MPLS_ROUTE_TAG = 100
VMB_MPLS_LOOPBACK_IP = f"{random_ipv4_address(net_seed=6, host_address=1)}/32"
VMB_MPLS_ROUTE_TAG = 200
DHCP_INTERFACE_NAME = "eth3"


@pytest.fixture(scope="class")
def l2_bridge_device_name(index_number):
    yield f"br{next(index_number)}test"


@pytest.fixture(scope="class")
def l2_bridge_device_worker_1(
    bridge_device_matrix__class__,
    nodes_available_nics,
    worker_node1,
    l2_bridge_device_name,
):
    with network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name=f"l2-bridge-{name_prefix(worker_node1.name)}",
        interface_name=l2_bridge_device_name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.name][-1]],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def l2_bridge_device_worker_2(
    bridge_device_matrix__class__,
    nodes_available_nics,
    worker_node2,
    l2_bridge_device_name,
):
    with network_device(
        interface_type=bridge_device_matrix__class__,
        nncp_name=f"l2-bridge-{name_prefix(worker_node2.name)}",
        interface_name=l2_bridge_device_name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[nodes_available_nics[worker_node2.name][-1]],
    ) as br:
        yield br


@pytest.fixture(scope="class")
def dhcp_nad(
    bridge_device_matrix__class__,
    namespace,
    l2_bridge_device_worker_1,
    l2_bridge_device_worker_2,
    l2_bridge_device_name,
    vlan_index_number,
):
    vlan_tag = next(vlan_index_number)
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name=f"{l2_bridge_device_name}-dhcp-broadcast-nad-vlan-{vlan_tag}",
        interface_name=l2_bridge_device_name,
        vlan=vlan_tag,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def custom_eth_type_llpd_nad(
    bridge_device_matrix__class__,
    namespace,
    l2_bridge_device_worker_1,
    l2_bridge_device_worker_2,
    l2_bridge_device_name,
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name=f"{l2_bridge_device_name}-custom-eth-type-icmp-nad",
        interface_name=l2_bridge_device_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def mpls_nad(
    bridge_device_matrix__class__,
    namespace,
    l2_bridge_device_worker_1,
    l2_bridge_device_worker_2,
    l2_bridge_device_name,
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name=f"{l2_bridge_device_name}-mpls-nad",
        interface_name=l2_bridge_device_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def dot1q_nad(
    bridge_device_matrix__class__,
    namespace,
    l2_bridge_device_worker_1,
    l2_bridge_device_worker_2,
    l2_bridge_device_name,
):
    with network_nad(
        namespace=namespace,
        nad_type=bridge_device_matrix__class__,
        nad_name=f"{l2_bridge_device_name}-dot1q-nad",
        interface_name=l2_bridge_device_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def l2_bridge_all_nads(dhcp_nad, custom_eth_type_llpd_nad, mpls_nad, dot1q_nad):
    return [custom_eth_type_llpd_nad.name, mpls_nad.name, dhcp_nad.name, dot1q_nad.name]


def _cloud_init_data(
    vm_name,
    ip_addresses,
    mpls_local_ip,
    mpls_local_tag,
    mpls_dest_ip,
    mpls_dest_tag,
    mpls_route_next_hop,
    cloud_init_extra_user_data,
):
    network_data_data = {
        "ethernets": {
            "eth1": {"addresses": [f"{ip_addresses[0]}/24"]},
            "eth2": {"addresses": [f"{ip_addresses[1]}/24"]},
            "eth4": {"addresses": [f"{ip_addresses[3]}/24"]},
        },
    }
    # Only DHCP server VM (vm-fedora-1) should have IP on eth3 interface
    if vm_name == "vm-fedora-1":
        network_data_data["ethernets"][DHCP_INTERFACE_NAME] = {"addresses": [f"{ip_addresses[2]}/24"]}

    # DHCP client VM (vm-fedora-2) should be with dhcp=false, will be activated in test 'test_dhcp_broadcast'.
    if vm_name == "vm-fedora-2":
        network_data_data["ethernets"][DHCP_INTERFACE_NAME] = {"dhcp4": False}

    runcmd = [
        "modprobe mpls_router",  # In order to test mpls we need to load driver
        "sysctl -w net.mpls.platform_labels=1000",  # Activate mpls labeling feature
        "sysctl -w net.mpls.conf.eth4.input=1",  # Allow incoming mpls traffic
        "sysctl -w net.ipv4.conf.all.arp_ignore=1",  # 2 kernel flags are used to disable wrong arp behavior
        "sysctl -w net.ipv4.conf.all.arp_announce=2",  # Send arp reply only if ip belongs to the interface
        f"ip addr add {mpls_local_ip} dev lo",
        f"ip -f mpls route add {mpls_local_tag} dev lo",
        "nmcli connection up eth4",  # In order to add mpls route we need to make sure that connection is UP
        f"ip route add {mpls_dest_ip} encap mpls {mpls_dest_tag} via inet {mpls_route_next_hop}",
        "nmcli connection up eth2",
        "ip route add 224.0.0.0/4 dev eth2",
    ]

    cloud_init_data = prepare_cloud_init_user_data(section="runcmd", data=runcmd)
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    if cloud_init_extra_user_data:
        update_cloud_init_extra_user_data(
            cloud_init_data=cloud_init_data["userData"],
            cloud_init_extra_user_data=cloud_init_extra_user_data,
        )

    return cloud_init_data


class VirtualMachineAttachedToBridge(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        interfaces,
        ip_addresses,
        mpls_local_tag,
        mpls_local_ip,
        mpls_dest_ip,
        mpls_dest_tag,
        mpls_route_next_hop,
        client=None,
        cloud_init_data=None,
        node_selector=None,
    ):
        self.cloud_init_data = cloud_init_data
        self.mpls_local_tag = mpls_local_tag
        self.ip_addresses = ip_addresses
        self.mpls_local_ip = ip_interface(address=mpls_local_ip).ip
        self.mpls_dest_ip = mpls_dest_ip
        self.mpls_dest_tag = mpls_dest_tag
        self.mpls_route_next_hop = mpls_route_next_hop

        networks = {}
        for network in interfaces:
            networks.update({network: network})

        super().__init__(
            name=name,
            namespace=namespace,
            interfaces=interfaces,
            networks=networks,
            client=client,
            cloud_init_data=cloud_init_data,
            node_selector=node_selector,
        )

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        super().to_dict()


@contextlib.contextmanager
def bridge_attached_vm(
    name,
    namespace,
    interfaces,
    ip_addresses,
    mpls_local_tag,
    mpls_dest_ip,
    mpls_dest_tag,
    mpls_route_next_hop,
    mpls_local_ip,
    cloud_init_extra_user_data=None,
    client=None,
    node_selector=None,
):
    cloud_init_data = _cloud_init_data(
        vm_name=name,
        ip_addresses=ip_addresses,
        mpls_local_ip=mpls_local_ip,
        mpls_local_tag=mpls_local_tag,
        mpls_dest_ip=mpls_dest_ip,
        mpls_dest_tag=mpls_dest_tag,
        mpls_route_next_hop=mpls_route_next_hop,
        cloud_init_extra_user_data=cloud_init_extra_user_data,
    )
    with VirtualMachineAttachedToBridge(
        namespace=namespace,
        name=name,
        interfaces=interfaces,
        ip_addresses=ip_addresses,
        mpls_local_tag=mpls_local_tag,
        mpls_local_ip=mpls_local_ip,
        mpls_dest_ip=mpls_dest_ip,
        mpls_dest_tag=mpls_dest_tag,
        mpls_route_next_hop=mpls_route_next_hop,
        client=client,
        cloud_init_data=cloud_init_data,
        node_selector=node_selector,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def l2_bridge_running_vm_a(
    namespace, worker_node1, l2_bridge_all_nads, dhcp_nad, unprivileged_client, l2_bridge_running_vm_b
):
    dhcpd_data = DHCP_SERVER_CONF_FILE.format(
        DHCP_IP_SUBNET=DHCP_IP_SUBNET,
        DHCP_IP_RANGE_START=DHCP_IP_RANGE_START,
        DHCP_IP_RANGE_END=DHCP_IP_RANGE_END,
        CLIENT_MAC_ADDRESS=get_vmi_mac_address_by_iface_name(vmi=l2_bridge_running_vm_b.vmi, iface_name=dhcp_nad.name),
    )
    cloud_init_extra_user_data = {
        "runcmd": [
            dhcpd_data,
            "sysctl net.ipv4.icmp_echo_ignore_broadcasts=0",  # Enable multicast support
        ]
    }

    interface_ip_addresses = [
        random_ipv4_address(net_seed=0, host_address=1),
        random_ipv4_address(net_seed=2, host_address=1),
        random_ipv4_address(net_seed=3, host_address=1),
        random_ipv4_address(net_seed=4, host_address=1),
    ]
    with bridge_attached_vm(
        name="vm-fedora-1",
        namespace=namespace.name,
        interfaces=l2_bridge_all_nads,
        ip_addresses=interface_ip_addresses,
        cloud_init_extra_user_data=cloud_init_extra_user_data,
        mpls_local_tag=VMA_MPLS_ROUTE_TAG,
        mpls_local_ip=VMA_MPLS_LOOPBACK_IP,
        mpls_dest_ip=VMB_MPLS_LOOPBACK_IP,
        mpls_dest_tag=VMB_MPLS_ROUTE_TAG,
        mpls_route_next_hop=random_ipv4_address(net_seed=4, host_address=2),
        client=unprivileged_client,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def l2_bridge_running_vm_b(namespace, worker_node2, l2_bridge_all_nads, unprivileged_client):
    interface_ip_addresses = [
        random_ipv4_address(net_seed=0, host_address=2),
        random_ipv4_address(net_seed=2, host_address=2),
        random_ipv4_address(net_seed=3, host_address=2),
        random_ipv4_address(net_seed=4, host_address=2),
    ]
    with bridge_attached_vm(
        name="vm-fedora-2",
        namespace=namespace.name,
        interfaces=l2_bridge_all_nads,
        ip_addresses=interface_ip_addresses,
        mpls_local_tag=VMB_MPLS_ROUTE_TAG,
        mpls_local_ip=VMB_MPLS_LOOPBACK_IP,
        mpls_dest_ip=VMA_MPLS_LOOPBACK_IP,
        mpls_dest_tag=VMA_MPLS_ROUTE_TAG,
        mpls_route_next_hop=random_ipv4_address(net_seed=4, host_address=1),
        client=unprivileged_client,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def eth3_nmcli_connection_uuid(l2_bridge_running_vm_b):
    rc, out, _ = l2_bridge_running_vm_b.ssh_exec.run_command(
        command=shlex.split(f"nmcli -g GENERAL.CON-UUID device show {DHCP_INTERFACE_NAME}")
    )
    assert not rc, "Could not extract connection uuid by device name"
    return out.strip()


@pytest.fixture(scope="class")
def configured_l2_bridge_vm_a(l2_bridge_running_vm_a):
    run_ssh_commands(
        host=l2_bridge_running_vm_a.ssh_exec,
        commands=[
            shlex.split(
                "sudo bash -c "
                + shlex.quote(f"cat > /etc/sysconfig/dhcpd <<'EOF'\nDHCPDARGS=\"{DHCP_INTERFACE_NAME}\"\nEOF")
            ),
            shlex.split(DHCP_SERVICE_RESTART),
        ],
    )
    verify_dhcpd_activated(vm=l2_bridge_running_vm_a)
    return l2_bridge_running_vm_a


@pytest.fixture()
def started_vmb_dhcp_client(l2_bridge_running_vm_b, eth3_nmcli_connection_uuid):
    nmcli_cmd = "sudo nmcli connection"
    # Start dhcp client in l2_bridge_running_vm_b
    run_ssh_commands(
        host=l2_bridge_running_vm_b.ssh_exec,
        commands=[
            shlex.split(f"{nmcli_cmd} modify '{eth3_nmcli_connection_uuid}' ipv4.method auto"),
            shlex.split(f"{nmcli_cmd} up '{eth3_nmcli_connection_uuid}'"),
            shlex.split("sudo systemctl restart qemu-guest-agent.service"),
        ],
    )
