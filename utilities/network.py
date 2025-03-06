import contextlib
import ipaddress
import logging
import os
import random
import re
import shlex

import netaddr
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.network_attachment_definition import (
    LinuxBridgeNetworkAttachmentDefinition,
    OVNOverlayNetworkAttachmentDefinition,
    OvsBridgeNetworkAttachmentDefinition,
)
from ocp_resources.network_config_openshift_io import Network
from ocp_resources.node import Node
from ocp_resources.node_network_configuration_policy import (
    NNCPConfigurationFailed,
    NodeNetworkConfigurationPolicy,
)
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.pod import Pod
from ocp_resources.sriov_network import SriovNetwork
from ocp_resources.sriov_network_node_policy import SriovNetworkNodePolicy
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

import utilities.infra
import utilities.virt
from utilities.constants import (
    ACTIVE_BACKUP,
    FLAT_OVERLAY_STR,
    IPV4_STR,
    IPV6_STR,
    LINUX_BRIDGE,
    MTU_9000,
    OVS_BRIDGE,
    SRIOV,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5SEC,
    TIMEOUT_8MIN,
    TIMEOUT_30SEC,
    WORKERS_TYPE,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import is_jira_open

LOGGER = logging.getLogger(__name__)
IFACE_UP_STATE = NodeNetworkConfigurationPolicy.Interface.State.UP
IFACE_ABSENT_STATE = NodeNetworkConfigurationPolicy.Interface.State.ABSENT
OVS_DS_NAME = "ovs-cni-amd64"
DEPLOY_OVS = "deployOVS"
BOND = "bond"
INPROGRESS = "InProgress"


class SriovIfaceNotFound(Exception):
    pass


class BridgeNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        bridge_name,
        bridge_type,
        stp_config,
        ports=None,
        mtu=None,
        node_selector=None,
        node_selector_labels=None,
        ipv4_enable=False,
        ipv4_dhcp=False,
        teardown=True,
        teardown_absent_ifaces=True,
        ipv6_enable=False,
        max_unavailable=None,
        set_ipv4=True,
        set_ipv6=True,
        dry_run=None,
        capture=None,
        routes=None,
        dns_resolver=None,
        bridge_state=IFACE_UP_STATE,
    ):
        """
        Create bridge on nodes (according node_selector, all if no selector presents)

        Args:
            name (str): Policy name.
            bridge_name (str): Bridge name.
            bridge_type (str): Bridge type (Linux Bridge, OVS)
            stp_config (bool): Spanning Tree enabled/disabled.
            ports (list): The bridge's port(s).
            mtu (int): MTU size
            ipv4_dhcp: determines if ipv4_dhcp should be used
            dry_run (str, default=None): If "All", the bridge will be created using the dry_run flag
        """
        super().__init__(
            name=name,
            node_selector=node_selector,
            node_selector_labels=node_selector_labels,
            teardown=teardown,
            teardown_absent_ifaces=teardown_absent_ifaces,
            mtu=mtu,
            ports=ports,
            ipv4_enable=ipv4_enable,
            ipv4_dhcp=ipv4_dhcp,
            ipv6_enable=ipv6_enable,
            max_unavailable=max_unavailable,
            set_ipv4=set_ipv4,
            set_ipv6=set_ipv6,
            dry_run=dry_run,
            capture=capture,
            routes=routes,
            dns_resolver=dns_resolver,
            state=bridge_state,
        )
        self.ovs_bridge_type = OVS_BRIDGE
        self.linux_bridge_type = LINUX_BRIDGE
        self.bridge_name = bridge_name
        self.bridge_type = bridge_type
        self.stp_config = stp_config

    @staticmethod
    def _does_port_match_type(nns, port_name, port_type):
        # From time to time the NNS interfaces take longer to get updated with the new port
        samples = TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=1,
            func=lambda: [_iface for _iface in nns.interfaces if _iface["name"] == port_name],
        )
        for sample in samples:
            if sample:
                return sample[0]["type"] == port_type

    def to_dict(self):
        bridge_ports = [{"name": port} for port in self.ports]
        stp = self.stp_config if self.bridge_type == self.ovs_bridge_type else {"enabled": self.stp_config}
        self.iface = {
            "name": self.bridge_name,
            "type": self.bridge_type,
            "state": self.state,
            "bridge": {
                "options": {"stp": stp},
                "port": bridge_ports,
            },
        }

        for port in bridge_ports:
            # OVS MTU handled in OvsBridgeNodeNetworkConfigurationPolicy
            if self.mtu and self.bridge_type != self.ovs_bridge_type:
                nns = NodeNetworkState(
                    name=utilities.infra.get_node_selector_name(node_selector=self.node_selector)
                    if self.node_selector
                    else self.nodes[0].name
                )
                port_name = port["name"]
                if self._does_port_match_type(nns=nns, port_name=port_name, port_type=BOND):
                    continue

                self.iface["mtu"] = self.mtu
                _port = {
                    "name": port_name,
                    "type": "ethernet",
                    "state": IFACE_UP_STATE,
                    "mtu": self.mtu,
                }
                self.set_interface(interface=_port)

        super().to_dict()


class LinuxBridgeNodeNetworkConfigurationPolicy(BridgeNodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        bridge_name,
        stp_config=False,
        ports=None,
        mtu=None,
        node_selector=None,
        node_selector_labels=None,
        ipv4_enable=False,
        ipv4_dhcp=False,
        teardown=True,
        teardown_absent_ifaces=True,
        set_ipv4=True,
        set_ipv6=True,
        max_unavailable=None,
        dry_run=None,
        capture=None,
        bridge_state=IFACE_UP_STATE,
        routes=None,
        dns_resolver=None,
    ):
        super().__init__(
            name=name,
            bridge_name=bridge_name,
            bridge_type=LINUX_BRIDGE,
            stp_config=stp_config,
            ports=ports,
            set_ipv4=set_ipv4,
            set_ipv6=set_ipv6,
            mtu=mtu,
            node_selector=node_selector,
            node_selector_labels=node_selector_labels,
            ipv4_enable=ipv4_enable,
            ipv4_dhcp=ipv4_dhcp,
            teardown=teardown,
            teardown_absent_ifaces=teardown_absent_ifaces,
            max_unavailable=max_unavailable,
            dry_run=dry_run,
            capture=capture,
            routes=routes,
            dns_resolver=dns_resolver,
            bridge_state=bridge_state,
        )


class OvsBridgeNodeNetworkConfigurationPolicy(BridgeNodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        bridge_name,
        ports,
        stp_config=False,
        mtu=None,
        node_selector=None,
        ipv4_enable=False,
        ipv4_dhcp=False,
        teardown=True,
        set_dummy_ovs_iface=False,
        set_port_mac=False,
        dry_run=None,
        node_selector_labels=None,
    ):
        super().__init__(
            name=name,
            bridge_name=bridge_name,
            bridge_type=OVS_BRIDGE,
            stp_config=stp_config,
            ports=ports,
            mtu=mtu,
            node_selector=node_selector,
            ipv4_enable=ipv4_enable,
            ipv4_dhcp=ipv4_dhcp,
            teardown=teardown,
            set_ipv4=False,
            set_ipv6=False,
            dry_run=dry_run,
            node_selector_labels=node_selector_labels,
        )
        self.set_dummy_ovs_iface = set_dummy_ovs_iface
        self.set_port_mac = set_port_mac

    @property
    def _nns_node(self):
        if self.node_selector:
            return list(
                Node.get(
                    dyn_client=self.client,
                    name=utilities.infra.get_node_selector_name(node_selector=self.node_selector),
                )
            )[0]
        else:
            return list(Node.get(dyn_client=self.client))[0]

    def to_dict(self):
        super().to_dict()
        if self.set_dummy_ovs_iface or self.mtu:
            desired_state_interface = self.res["spec"]["desiredState"]["interfaces"]
            for idx, iface in enumerate(desired_state_interface):
                if iface["type"] == self.ovs_bridge_type:
                    ovs_dummy_interface_name = f"ovs-dummy{idx}"
                    port_name = iface["bridge"]["port"][0]["name"]

                    if self.mtu:
                        nns = NodeNetworkState(name=self._nns_node.name)
                        if BridgeNodeNetworkConfigurationPolicy._does_port_match_type(
                            nns=nns, port_name=port_name, port_type=BOND
                        ):
                            continue

                        port_iface = {
                            "name": port_name,
                            "type": "ethernet",
                            "state": IFACE_UP_STATE,
                            "ipv4": {"enabled": False},
                            "mtu": self.mtu,
                        }
                        desired_state_interface.append(port_iface)

                    if self.set_dummy_ovs_iface:
                        iface["bridge"]["port"].append({"name": ovs_dummy_interface_name})
                        ovs_iface = {
                            "name": ovs_dummy_interface_name,
                            "type": "ovs-interface",
                            "state": IFACE_UP_STATE,
                            "ipv4": {
                                "enabled": self.ipv4_enable,
                                "dhcp": self.ipv4_dhcp,
                            },
                            "mtu": self.mtu,
                        }
                        if self.set_port_mac:
                            if not self.node_selector:
                                raise ValueError("node_selector is required for set_port_mac")

                            nns = NodeNetworkState(
                                name=utilities.infra.get_node_selector_name(node_selector=self.node_selector)
                            )
                            port_mac = [iface["mac-address"] for iface in nns.interfaces if iface["name"] == port_name]
                            ovs_iface["mac-address"] = port_mac[0]

                        desired_state_interface.append(ovs_iface)

            self.res["spec"]["desiredState"]["interfaces"] = desired_state_interface

    def deploy(self, wait=False):
        try:
            return super().deploy(wait=wait)
        except NNCPConfigurationFailed as exp:
            if "failed to communicating with Open vSwitch database" in str(exp):
                LOGGER.warning("W/A for ovs-bridge when OVS DB is locked")
                self.res = self.to_dict()
                return super().deploy(wait=wait)
            raise


class VLANInterfaceNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        iface_state,
        base_iface,
        tag,
        name=None,
        node_selector=None,
        ipv4_enable=False,
        ipv4_dhcp=False,
        teardown=True,
        ipv6_enable=False,
        dry_run=None,
        node_selector_labels=None,
    ):
        # Given NNCP's 15-char limit, use only the last 4 chars of interface names.
        iface_name = f"{base_iface[-4:]}.{tag}"
        if not name:
            name = f"{iface_name}-nncp"

        super().__init__(
            name=name,
            node_selector=node_selector,
            teardown=teardown,
            ipv4_enable=ipv4_enable,
            ipv4_dhcp=ipv4_dhcp,
            ipv6_enable=ipv6_enable,
            dry_run=dry_run,
            node_selector_labels=node_selector_labels,
        )
        self.iface_state = iface_state
        self.base_iface = base_iface
        self.tag = tag
        self.iface_name = iface_name
        self.iface = None

    def to_dict(self):
        self.iface = {
            "name": self.iface_name,
            "type": "vlan",
            "state": self.iface_state,
        }
        vlan_spec = {"vlan": {"base-iface": self.base_iface, "id": self.tag}}
        self.iface.update(vlan_spec)
        super().to_dict()


class BondNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        bond_name,
        bond_ports,
        mode=ACTIVE_BACKUP,
        mtu=None,
        primary_bond_port=None,
        node_selector=None,
        teardown=True,
        ipv4_enable=False,
        ipv4_dhcp=False,
        ipv6_enable=False,
        options=None,
        dry_run=None,
        success_timeout=TIMEOUT_8MIN,
        teardown_absent_ifaces=True,
    ):
        super().__init__(
            name=name,
            node_selector=node_selector,
            teardown=teardown,
            mtu=mtu,
            ipv4_enable=ipv4_enable,
            ipv4_dhcp=ipv4_dhcp,
            ipv6_enable=ipv6_enable,
            dry_run=dry_run,
            success_timeout=success_timeout,
            teardown_absent_ifaces=teardown_absent_ifaces,
        )
        self.bond_name = bond_name
        self.bond_ports = bond_ports
        self.mode = mode
        self.primary_bond_port = primary_bond_port
        self.ports = self.bond_ports
        self.options = options
        # PSI MTU cannot be greater than 1450
        if os.environ.get(WORKERS_TYPE) == utilities.infra.ClusterHosts.Type.VIRTUAL and not self.mtu:
            self.mtu = 1450

    def create_interface(self):
        options_dic = self.options or {}
        options_dic.update({"miimon": "120"})
        if self.mode == ACTIVE_BACKUP and self.primary_bond_port is not None:
            options_dic.update({"primary": self.primary_bond_port})

        self.iface = {
            "name": self.bond_name,
            "type": BOND,
            "state": NodeNetworkConfigurationPolicy.Interface.State.UP,
            "link-aggregation": {
                "mode": self.mode,
                "port": self.bond_ports,
                "options": options_dic,
            },
        }

    def configure_mtu_on_ports(self):
        if self.mtu:
            self.iface["mtu"] = self.mtu
        for port in self.ports:
            _port = {
                "name": port,
                "type": "ethernet",
                "state": NodeNetworkConfigurationPolicy.Interface.State.UP,
            }
            if self.mtu:
                _port["mtu"] = self.mtu
            self.set_interface(interface=_port)

    def to_dict(self):
        super().to_dict()
        if not self.iface:
            self.create_interface()
            self.add_interface(
                iface=self.iface,
                ipv4_enable=self.ipv4_enable,
                ipv4_dhcp=self.ipv4_dhcp,
                ipv6_enable=self.ipv6_enable,
            )

            if self.mtu:
                self.configure_mtu_on_ports()


NETWORK_DEVICE_TYPE = {
    LINUX_BRIDGE: LinuxBridgeNodeNetworkConfigurationPolicy,
    OVS_BRIDGE: OvsBridgeNodeNetworkConfigurationPolicy,
    SRIOV: SriovNetworkNodePolicy,
}
NAD_TYPE = {
    LINUX_BRIDGE: LinuxBridgeNetworkAttachmentDefinition,
    OVS_BRIDGE: OvsBridgeNetworkAttachmentDefinition,
    SRIOV: SriovNetwork,
    FLAT_OVERLAY_STR: OVNOverlayNetworkAttachmentDefinition,
}


def get_vmi_ip_v4_by_name(vm, name):
    vmi = vm.vmi

    def _get_iface_by_name(vmi_interfaces):
        iface = [_iface for _iface in vmi_interfaces if _iface.name == name]
        if not iface:
            raise IfaceNotFound(name=name)
        return iface[0]

    def _extract_interface_ips():
        vmi_interfaces = vm.vmi.interfaces
        iface_ips = _get_iface_by_name(vmi_interfaces=vmi_interfaces).ipAddresses
        if iface_ips:
            return iface_ips
        return []

    def _get_interface_ips():
        vmi_ips = _extract_interface_ips()
        if vmi_ips:
            return vmi_ips

        utilities.virt.wait_for_vm_interfaces(vmi=vmi)
        return _extract_interface_ips()

    # TODO: Investigate why on BMs (bm02+03-cnvqe2-rdu2) it takes so long for the IP to be seen in the VMI.
    # When Jira ticket CNV-19348 is closed: 1. Revert the wait_timout back to 2 minutes; 2. the check of the
    # workers_type is redundant.
    wait_timeout = (
        TIMEOUT_8MIN
        if (
            (os.environ[WORKERS_TYPE] == utilities.infra.ClusterHosts.Type.PHYSICAL)
            and is_jira_open(jira_id="CNV-19348")
        )
        else TIMEOUT_2MIN
    )
    sampler = TimeoutSampler(wait_timeout=wait_timeout, sleep=1, func=_get_interface_ips)
    try:
        for ip_addresses in sampler:
            for ip_address in ip_addresses:
                ip = ipaddress.ip_interface(address=ip_address)
                if ip.version == 4:
                    return ip.ip

    except TimeoutExpiredError:
        raise IpNotFound(name)


class IpNotFound(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"IP address not found for interface {self.name}"


@contextlib.contextmanager
def network_nad(
    nad_type,
    nad_name,
    namespace,
    interface_name=None,
    tuning=None,
    vlan=None,
    mtu=None,
    ipam=None,
    macspoofchk=None,
    sriov_resource_name=None,
    sriov_network_namespace=None,
    network_name=None,
    topology=None,
    add_resource_name=True,
    teardown=True,
):
    kwargs = {
        "name": nad_name,
        "namespace": namespace.name,
        "teardown": teardown,
        "vlan": vlan,
    }
    if nad_type == LINUX_BRIDGE:
        kwargs["cni_type"] = py_config["linux_bridge_cni"]
        kwargs["tuning_type"] = py_config["bridge_tuning"] if tuning else None
        kwargs["bridge_name"] = interface_name
        kwargs["mtu"] = mtu
        kwargs["macspoofchk"] = macspoofchk
        kwargs["add_resource_name"] = add_resource_name

    if nad_type == SRIOV:
        kwargs["network_namespace"] = sriov_network_namespace
        kwargs["resource_name"] = sriov_resource_name
        kwargs["ipam"] = ipam
        kwargs["macspoofchk"] = macspoofchk

    if nad_type == OVS_BRIDGE:
        kwargs["bridge_name"] = interface_name
        kwargs["mtu"] = mtu

    if nad_type == FLAT_OVERLAY_STR:
        kwargs["network_name"] = network_name
        kwargs["topology"] = topology
        kwargs["mtu"] = mtu

    with NAD_TYPE[nad_type](**kwargs) as nad:
        yield nad


class EthernetNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name,
        interfaces_name=None,
        iface_state=NodeNetworkConfigurationPolicy.Interface.State.UP,
        node_selector=None,
        teardown=True,
        teardown_absent_ifaces=True,
        ipv4_enable=False,
        ipv4_dhcp=False,
        ipv4_auto_dns=True,
        ipv4_addresses=None,
        ipv6_dhcp=False,
        ipv6_auto_dns=True,
        ipv6_enable=False,
        ipv6_addresses=None,
        dns_resolver=None,
        routes=None,
        dry_run=None,
        success_timeout=TIMEOUT_8MIN,
    ):
        super().__init__(
            name=name,
            node_selector=node_selector,
            state=iface_state,
            ipv4_enable=ipv4_enable,
            ipv4_dhcp=ipv4_dhcp,
            ipv4_addresses=ipv4_addresses,
            ipv6_dhcp=ipv6_dhcp,
            ipv6_auto_dns=ipv6_auto_dns,
            ipv6_enable=ipv6_enable,
            ipv6_addresses=ipv6_addresses,
            teardown=teardown,
            teardown_absent_ifaces=teardown_absent_ifaces,
            dns_resolver=dns_resolver,
            routes=routes,
            dry_run=dry_run,
            success_timeout=success_timeout,
        )
        self.interfaces_name = interfaces_name
        self.ipv4_auto_dns = ipv4_auto_dns

    def to_dict(self):
        super().to_dict()
        if self.interfaces_name:
            for nic in self.interfaces_name:
                self.iface = {
                    "name": nic,
                    "type": "ethernet",
                    "state": self.state,
                    "ipv4": {
                        "auto-dns": self.ipv4_auto_dns,
                    },
                }
                self.set_interface(interface=self.iface)
                super().to_dict()


def sriov_network_dict(namespace, network):
    """
    This function returns sriov network dictionary passed as an argument during vm creation
    """
    return {network.name: f"{namespace.name}/{network.name}"}


class MacPool:
    """
    Class to manage the mac addresses pool.
    to get this class, use mac_pool fixture.
    whenever you create a VM, before yield, call: mac_pool.append_macs(vm)
    and after yield, call: mac_pool.remove_macs(vm).
    """

    def __init__(self, kmp_range):
        self.range_start = self.mac_to_int(mac=kmp_range["RANGE_START"])
        self.range_end = self.mac_to_int(mac=kmp_range["RANGE_END"])
        self.pool = range(self.range_start, self.range_end + 1)
        self.used_macs = []

    def get_mac_from_pool(self):
        return self.mac_sampler(func=random.choice, seq=self.pool)

    def mac_sampler(self, func, *args, **kwargs):
        sampler = TimeoutSampler(wait_timeout=20, sleep=1, func=func, *args, **kwargs)
        for sample in sampler:
            mac = self.int_to_mac(num=sample)
            if mac not in self.used_macs:
                return mac

    @staticmethod
    def mac_to_int(mac):
        return int(netaddr.EUI(mac))

    @staticmethod
    def int_to_mac(num):
        mac = netaddr.EUI(num)
        mac.dialect = netaddr.mac_unix_expanded
        return str(mac)

    def append_macs(self, vm):
        for iface in vm.get_interfaces():
            self.used_macs.append(iface["macAddress"])

    def remove_macs(self, vm):
        for iface in vm.get_interfaces():
            self.used_macs.remove(iface["macAddress"])

    def mac_is_within_range(self, mac):
        return self.mac_to_int(mac) in self.pool


class IfaceNotFound(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"Interface not found for NAD {self.name}"


def get_vmi_mac_address_by_iface_name(vmi, iface_name):
    for iface in vmi.interfaces:
        if iface.name == iface_name:
            return iface.mac
    raise IfaceNotFound(name=iface_name)


def cloud_init_network_data(data):
    """
    Generate cloud init network data.
    https://cloudinit.readthedocs.io/en/latest/topics/network-config-format-v2.html

    data (dict): Dict of interface name and ip addresses.

    Examples:
        data = {
            "ethernets": {
                "eth1": {"addresses": ["192.168.10.1/24"]},
                "vlans": {
                    "eth1.10": {"addresses": ["192.168.10.3/24"], "id": 1000, "link": "eth1"}
                },
            }
        }
        network_data = cloud_init_network_data(data=data)
    """
    network_data = {"networkData": {"version": 2}}
    network_data["networkData"].update(data)

    return network_data


def ping(src_vm, dst_ip, packet_size=None, count=None, quiet_output=True, interface=None):
    """
    Ping from source VM to destination IP.

    Args:
        src_vm: Source VM to execute the ping from.
        dst_ip: Destination ip to ping.
        packet_size: Number of data bytes to send.
        count: Amount of packets.
        quiet_output: Quiet output, Nothing is displayed except the summary lines at startup time and when finished.
        interface: interface (ping -I option)

    Returns:
        float or None: The packet loss amount in a number (Range - 0 to 100).
    """
    ping_ipv6 = "-6" if get_valid_ip_address(dst_ip=dst_ip, family=IPV6_STR) else ""

    ping_cmd = f"ping {'-q' if quiet_output else ''} {ping_ipv6} -c {count if count else '3'} {dst_ip}"
    if packet_size:
        ping_cmd += f" -s {packet_size} -M do"
    if interface:
        ping_cmd += f" -I {interface}"

    _, out, err = src_vm.ssh_exec.run_command(command=shlex.split(ping_cmd))
    out_to_process = err or out
    match = re.search(r"(\d*\.?\d+)%", out_to_process)
    if match:
        LOGGER.info(f"ping returned {match.string.strip()}")
        return float(match.group(1))


def assert_ping_successful(
    src_vm,
    dst_ip,
    packet_size=None,
    count=None,
    interface=None,
):
    if packet_size and packet_size > 1500:
        # ICMP packet reductions:
        icmp_header = 8
        ip_header = 20
        packet_size = packet_size - ip_header - icmp_header
    assert (
        ping(
            src_vm=src_vm,
            dst_ip=dst_ip,
            packet_size=packet_size,
            count=count,
            interface=interface,
        )
        == 0
    )


def get_ip_from_vm_or_virt_handler_pod(family, vm=None, virt_handler_pod=None):
    """
    Attempt to find an IP in one of 2 possible sources - VirtualMachine or virt-handler Pod.

     Args:
        vm (object): the VM which IP address is requested
        virt_handler_pod (pod): a virt-handler pod which IP address is requested
        family (str): IP version requested - "ipv4" or "ipv6"

    Returns:
        str or None: First found valid IP version address, or None.
    """
    if not (vm or virt_handler_pod):
        raise ValueError("must send VM or virt-handler pod")

    if vm:
        addr_list = vm.vmi.interfaces[0]["ipAddresses"]
    else:
        addr_list = [ip_addr["ip"] for ip_addr in virt_handler_pod.instance.status.podIPs]

    ip_list = [ip for ip in addr_list if get_valid_ip_address(dst_ip=ip, family=family)]
    return ip_list[0] if ip_list else None


def get_valid_ip_address(dst_ip, family):
    """
    Return the IP address string if the input address is either IPv4 or IPv6 address, else None.

    Args:
        family (str): IP version requested - "ipv4" or "ipv6"

    Returns:
        str or None: If IP is valid - return IP, if not - return None
    """
    try:
        return ipaddress.IPv4Address(address=dst_ip) if family == IPV4_STR else ipaddress.IPv6Address(address=dst_ip)
    except ipaddress.AddressValueError:
        return


def ip_version_data_from_matrix(request):
    """
    Check if fixture ip_stack_version_matrix__<scope>__ is used in the flow, to indicate whether
    it's a dual-stack test or not.

    Args:
        request (fixtures.SubRequest): Test's parameterized request.

    Returns:
        str: The IP family (IPv4 or IPv6) if the matrix fixture is used, else None.
    """
    ip_stack_matrix_fixture = [fix_name for fix_name in request.fixturenames if "ip_stack_version_matrix__" in fix_name]
    if not ip_stack_matrix_fixture:
        return
    return request.getfixturevalue(ip_stack_matrix_fixture[0])


def compose_cloud_init_data_dict(network_data=None, ipv6_network_data=None):
    init_data = {}
    interfaces_data = {"ethernets": {}}
    for data_input in [network_data, ipv6_network_data]:
        if data_input:
            interfaces_data["ethernets"].update(data_input["ethernets"])

    if interfaces_data["ethernets"]:
        init_data.update(cloud_init_network_data(data=interfaces_data))
    return init_data


def ovs_pods(admin_client, hco_namespace):
    pods = utilities.infra.get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=OVS_DS_NAME,
        namespace=hco_namespace,
        get_all=True,
    )
    return [pod for pod in pods or [] if pod.instance.status.phase == Pod.Status.RUNNING]


def wait_for_ovs_pods(admin_client, hco_namespace, count=0):
    LOGGER.info(f"Wait for number of OVS pods to be: {count}")
    samples = TimeoutSampler(
        wait_timeout=150,
        sleep=1,
        func=ovs_pods,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    num_of_pods = None
    try:
        for sample in samples:
            num_of_pods = len(sample)
            if num_of_pods == count:
                return True

    except TimeoutExpiredError:
        LOGGER.error(f"Found {num_of_pods} OVS PODs, expected: {count}")
        raise


def wait_for_ovs_status(network_addons_config, status=True):
    opt_log = "opt-in" if status else "opt-out"
    resource_log = f"{network_addons_config.kind} {network_addons_config.name}"
    LOGGER.info(f"Wait for {resource_log} OVS to be {opt_log}")
    samples = TimeoutSampler(
        wait_timeout=60,
        sleep=1,
        func=lambda: network_addons_config.instance.spec.ovs,
    )

    try:
        for sample in samples:
            # sample is {} when opt-out
            if bool(sample) == status:
                return True

    except TimeoutExpiredError:
        LOGGER.error(f"{resource_log} OVS should be {opt_log}")
        raise


def verify_ovs_installed_with_annotations(
    admin_client,
    ovs_daemonset,
    hyperconverged_ovs_annotations_fetched,
    network_addons_config,
):
    # Verify OVS
    wait_for_ovs_status(network_addons_config=network_addons_config)
    assert ovs_daemonset.exists, f"{OVS_DS_NAME} not found."
    ovs_daemonset.wait_until_deployed()
    # Verify annotations
    assert hyperconverged_ovs_annotations_fetched, "No ovs annotations found."
    # Verify pods
    wait_for_ovs_pods(
        admin_client=admin_client,
        hco_namespace=ovs_daemonset.namespace,
        count=ovs_daemonset.instance.status.desiredNumberScheduled,
    )


def get_ovs_daemonset(admin_client, hco_namespace):
    return utilities.infra.get_daemonset_by_name(
        admin_client=admin_client,
        daemonset_name=OVS_DS_NAME,
        namespace_name=hco_namespace.name,
    )


def wait_for_ovs_daemonset_deleted(ovs_daemonset):
    samples = TimeoutSampler(wait_timeout=90, sleep=1, func=lambda: ovs_daemonset.exists)
    try:
        for sample in samples:
            if not sample:
                return True

    except TimeoutExpiredError:
        LOGGER.error("OVS daemonset exists after opt-out")
        raise


def wait_for_ovs_daemonset_resource(admin_client, hco_namespace):
    samples = TimeoutSampler(
        wait_timeout=30,
        sleep=1,
        func=get_ovs_daemonset,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    try:
        for sample in samples:
            if sample:
                return sample

    except TimeoutExpiredError:
        LOGGER.error("OVS daemonset doesn't exists after opt-in")
        raise


@contextlib.contextmanager
def network_device(
    interface_type,
    nncp_name,
    interface_name=None,
    ports=None,
    mtu=None,
    node_selector=None,
    ipv4_enable=False,
    ipv4_dhcp=False,
    priority=None,
    namespace=None,
    sriov_iface=None,
    sriov_resource_name=None,
    node_selector_labels=None,
):
    kwargs = {
        "name": nncp_name,
        "mtu": mtu,
    }
    if interface_type == SRIOV:
        kwargs["namespace"] = namespace
        kwargs["resource_name"] = sriov_resource_name
        kwargs["pf_names"] = sriov_iface.name
        kwargs["root_devices"] = sriov_iface.pciAddress
        # num_vfs is the pool of ifaces we want available in the sriov network
        # and should be no less than the number of multiple vm's we use in the tests
        # totalvfs is usually 64 or 128
        kwargs["num_vfs"] = min(sriov_iface.totalvfs, 10)
        kwargs["priority"] = priority or 99

    else:
        kwargs["bridge_name"] = interface_name
        kwargs["ports"] = ports
        kwargs["node_selector"] = node_selector
        kwargs["ipv4_enable"] = ipv4_enable
        kwargs["ipv4_dhcp"] = ipv4_dhcp
        kwargs["node_selector_labels"] = node_selector_labels

    with NETWORK_DEVICE_TYPE[interface_type](**kwargs) as iface:
        yield iface


def enable_hyperconverged_ovs_annotations(
    admin_client,
    hco_namespace,
    hyperconverged_resource,
    network_addons_config,
):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource: {"metadata": {"annotations": {DEPLOY_OVS: "true"}}}},
        list_resource_reconcile=[NetworkAddonsConfig],
        wait_for_reconcile_post_update=True,
    ):
        wait_for_ovs_status(network_addons_config=network_addons_config, status=True)
        ovs_daemonset = wait_for_ovs_daemonset_resource(admin_client=admin_client, hco_namespace=hco_namespace)
        ovs_daemonset.wait_until_deployed()
        yield ovs_daemonset


def cloud_init(ip_address):
    network_data_data = {"ethernets": {"eth1": {"addresses": [f"{ip_address}/24"]}}}
    return cloud_init_network_data(data=network_data_data)


def is_destination_pingable_from_vm(
    src_vm,
    dst_ip,
    count,
    interface=None,
):
    ping_stat = ping(
        src_vm=src_vm,
        dst_ip=dst_ip,
        count=count,
        interface=interface,
    )
    return ping_stat < 100


def get_cluster_cni_type(admin_client):
    return Network(client=admin_client, name="cluster").instance.status.networkType


def wait_for_ready_sriov_nodes(snns):
    for status in (INPROGRESS, SriovNetworkNodePolicy.Status.SUCCEEDED):
        for sriov_node_network_state in snns:
            LOGGER.info(f"Checking state: {sriov_node_network_state.name}")
            try:
                sriov_node_network_state.wait_for_status_sync(wanted_status=status)
            except TimeoutExpiredError:
                if (
                    status == INPROGRESS
                    and sriov_node_network_state.instance.status.syncStatus == SriovNetworkNodePolicy.Status.SUCCEEDED
                ):
                    continue
                else:
                    LOGGER.error(
                        f"Current status: {sriov_node_network_state.instance.status.syncStatus} expected: {status}"
                    )
                    raise


def create_sriov_node_policy(
    nncp_name,
    namespace,
    sriov_iface,
    sriov_nodes_states,
    sriov_resource_name,
    mtu=MTU_9000,
):
    with network_device(
        interface_type=SRIOV,
        nncp_name=nncp_name,
        namespace=namespace,
        sriov_iface=sriov_iface,
        sriov_resource_name=sriov_resource_name,
        # sriov operator doesnt pass the mtu to the VFs when using vfio-pci device driver (the one we are using)
        # so the mtu parameter only affects the PF. we need to change the mtu manually on the VM.
        mtu=mtu,
    ) as policy:
        wait_for_ready_sriov_nodes(snns=sriov_nodes_states)
        yield policy
    wait_for_ready_sriov_nodes(snns=sriov_nodes_states)


def verify_dhcpd_activated(vm):
    active = "active"
    dhcpd = "dhcpd"
    sample = None
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_30SEC,
        sleep=TIMEOUT_5SEC,
        func=run_ssh_commands,
        host=vm.ssh_exec,
        commands=[shlex.split(f"sudo systemctl is-{active} {dhcpd}")],
    )
    try:
        for sample in sampler:
            if sample[0].strip() == active:
                return True

    except TimeoutExpiredError:
        LOGGER.error(f"{dhcpd} status is not '{active}' but rather '{sample}'")
        raise


def wait_for_node_marked_by_bridge(bridge_nad: LinuxBridgeNetworkAttachmentDefinition, node: Node) -> None:
    bridge_annotation = bridge_nad.resource_name
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=5,
        func=lambda: bridge_annotation in node.instance.status.capacity.keys()
        and bridge_annotation in node.instance.status.allocatable.keys(),
    )
    try:
        for sample in sampler:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Node {node.hostname} is not marked by {bridge_nad.bridge_name} bridge")
        raise
