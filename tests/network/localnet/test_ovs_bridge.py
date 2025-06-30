import pytest

from libs.net.traffic_generator import is_tcp_connection
from utilities.virt import migrate_vm_and_verify
from ocp_resources.resource import ResourceEditor
from .liblocalnet import LOCALNET_OVS_BRIDGE_NETWORK
from tests.network.localnet.liblocalnet import (
    create_traffic_client,
    create_traffic_server,
    run_vms,
)
from utilities.network import IfaceNotFound
from typing import Final

_DEFAULT_CMD_TIMEOUT_SEC: Final[int] = 10


def patch_localnet_interface(vm, state):
    vmi_interfaces = vm.get_interfaces()
    interfaces_list = []
    interface_to_patch = ""
    for interface in vmi_interfaces:
        interface_dict = dict(interface)
        if interface_dict["name"] == LOCALNET_OVS_BRIDGE_NETWORK:
            interface_to_patch = interface_dict["name"]
            interface_dict["state"] = state
        interfaces_list.append(interface_dict)
    if interface_to_patch == "":
        raise IfaceNotFound(name=LOCALNET_OVS_BRIDGE_NETWORK)
    patch_interface_state(vm, interfaces_list)


def patch_interface_state(vm, interfaces):
    patches = {
        vm: {
            "spec": {
                "template": {
                    "spec": {
                        "domain": {
                            "devices": {
                                "interfaces": interfaces
                            }
                        }
                    }
                }
            }
        }
    }
    ResourceEditor(patches=patches).update()


def get_link_state_of_interface(vm, interface_name):
    linkstate = ""
    for interface in vm.vmi.instance.status.interfaces:
        if interface["name"] == interface_name:
            linkstate = interface["linkState"]
    return linkstate


@pytest.mark.ipv4
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-11905")
def test_connectivity_over_migration_between_ovs_bridge_localnet_vms(
    localnet_ovs_bridge_server, localnet_ovs_bridge_client
):
    migrate_vm_and_verify(vm=localnet_ovs_bridge_client.vm)
    assert is_tcp_connection(server=localnet_ovs_bridge_server, client=localnet_ovs_bridge_client)


@pytest.mark.ipv4
@pytest.mark.usefixtures("nncp_localnet_on_secondary_node_nic")
@pytest.mark.polarion("CNV-11905")
def test_connectivity_after_interface_state_change_in_ovs_bridge_localnet_vms(
    vm_ovs_bridge_localnet_no_ip, vm_ovs_bridge_localnet_2
):

    run_vms(vms=(vm_ovs_bridge_localnet_no_ip, vm_ovs_bridge_localnet_2))
    link_state = get_link_state_of_interface(vm_ovs_bridge_localnet_no_ip,
                                             LOCALNET_OVS_BRIDGE_NETWORK)
    assert link_state == "down"
    patch_localnet_interface(vm_ovs_bridge_localnet_no_ip, "up")
    link_state = get_link_state_of_interface(vm_ovs_bridge_localnet_no_ip,
                                             LOCALNET_OVS_BRIDGE_NETWORK)
    assert link_state == "up"
    result=vm_ovs_bridge_localnet_no_ip.console(commands=["ip link show dev eth0"], timeout=_DEFAULT_CMD_TIMEOUT_SEC)

    server = create_traffic_server(vm=vm_ovs_bridge_localnet_no_ip)
    client = create_traffic_client(
        server_vm=vm_ovs_bridge_localnet_no_ip,
        client_vm=vm_ovs_bridge_localnet_2,
        spec_logical_network=LOCALNET_OVS_BRIDGE_NETWORK,)
    assert is_tcp_connection(server=server, client=client)
