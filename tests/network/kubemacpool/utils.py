import logging
from collections import namedtuple
from ipaddress import ip_interface

from libs.net.ip import random_ipv4_address
from libs.vm.guest import guest_iface_name
from utilities.network import cloud_init_network_data, get_vmi_mac_address_by_iface_name
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    prepare_cloud_init_user_data,
)

LOGGER = logging.getLogger(__name__)
KMP_PODS_LABEL = "control-plane=mac-controller-manager"
IfaceTuple = namedtuple("IfaceTuple", ["ip_address", "mac_address", "name"])


def vm_network_config(mac_pool, all_nads, end_ip_octet, mac_uid):
    """
    Args:
        end_ip_octet(int): int in range [1,254]
        mac_uid(str): string in range ['0','f'] in hex

    Returns:
        dict: key - interface name.
              value - IP address, MAC address, network name.
    """
    return {
        guest_iface_name(ordinal=2): IfaceTuple(
            ip_address=random_ipv4_address(net_seed=0, host_address=end_ip_octet),
            mac_address=mac_pool.get_mac_from_pool(),
            name=all_nads[0],
        ),
        guest_iface_name(ordinal=3): IfaceTuple(
            ip_address=random_ipv4_address(net_seed=1, host_address=end_ip_octet),
            mac_address="auto",
            name=all_nads[1],
        ),
        guest_iface_name(ordinal=4): IfaceTuple(
            ip_address=random_ipv4_address(net_seed=2, host_address=end_ip_octet),
            mac_address=f"02:0{mac_uid}:00:00:00:00",
            name=all_nads[2],
        ),
        guest_iface_name(ordinal=5): IfaceTuple(
            ip_address=random_ipv4_address(net_seed=3, host_address=end_ip_octet),
            mac_address="auto",
            name=all_nads[3],
        ),
    }


def create_vm(name, namespace, iface_config, node_selector, client, mac_pool):
    network_data_data = {}
    _data = {
        iface: {"addresses": [f"{iface_config[iface].ip_address}/24"]}
        for iface in ("eth%d" % idx for idx in range(1, 5))
    }
    runcmd = [
        # 2 kernel flags are used to disable wrong arp behavior
        "sysctl -w net.ipv4.conf.all.arp_ignore=1",
        # Send arp reply only if ip belongs to the interface
        "sysctl -w net.ipv4.conf.all.arp_announce=2",
    ]

    cloud_init_data = prepare_cloud_init_user_data(section="runcmd", data=runcmd)

    network_data_data["ethernets"] = _data
    cloud_init_data.update(cloud_init_network_data(data=network_data_data))

    with VirtualMachineWithMultipleAttachments(
        namespace=namespace.name,
        name=name,
        iface_config=iface_config,
        node_selector=node_selector,
        client=client,
        cloud_init_data=cloud_init_data,
    ) as vm:
        mac_pool.append_macs(vm=vm)
        yield vm
        mac_pool.remove_macs(vm=vm)


class VirtualMachineWithMultipleAttachments(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        iface_config,
        node_selector,
        client=None,
        cloud_init_data=None,
    ):
        self.iface_config = iface_config

        networks = {}
        for config in self.iface_config.values():
            networks[config.name] = config.name

        super().__init__(
            name=name,
            namespace=namespace,
            networks=networks,
            node_selector=node_selector,
            interfaces=networks.keys(),
            client=client,
            cloud_init_data=cloud_init_data,
        )

    @property
    def default_masquerade_iface_config(self):
        pod_iface_config = self.vmi.instance["status"]["interfaces"][0]
        return IfaceTuple(
            ip_address=ip_interface(pod_iface_config["ipAddress"]).ip,
            mac_address="auto",
            name=pod_iface_config["name"],
        )

    @property
    def manual_mac_iface_config(self):
        return self.iface_config[guest_iface_name(ordinal=2)]

    @property
    def auto_mac_iface_config(self):
        return self.iface_config[guest_iface_name(ordinal=3)]

    @property
    def manual_mac_out_pool_iface_config(self):  # Manually assigned mac out of pool
        return self.iface_config[guest_iface_name(ordinal=4)]

    @property
    def auto_mac_tuning_iface_config(self):
        return self.iface_config[guest_iface_name(ordinal=5)]

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        super().to_dict()
        for mac, iface in zip(
            self.iface_config.values(),
            self.res["spec"]["template"]["spec"]["domain"]["devices"]["interfaces"][1:],
        ):
            if mac.mac_address != "auto":
                iface["macAddress"] = mac.mac_address


def assert_macs_preseved(vm):
    for iface in vm.get_interfaces():
        assert iface.macAddress == get_vmi_mac_address_by_iface_name(vmi=vm.vmi, iface_name=iface.name)


def assert_manual_mac_configured(vm, iface_config):
    assert iface_config.mac_address == get_vmi_mac_address_by_iface_name(vmi=vm.vmi, iface_name=iface_config.name)
