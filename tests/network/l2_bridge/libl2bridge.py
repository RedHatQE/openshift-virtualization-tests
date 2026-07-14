import contextlib
import ipaddress
import json
import logging
import re
import time
from ipaddress import ip_interface
from typing import Final

from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.resource import ResourceField
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from libs.net.ip import random_ipv4_address
from libs.net.vmspec import (
    IpNotFound,
    VMInterfaceStatusNotFoundError,
    lookup_iface_status,
    lookup_iface_status_ip,
    wait_for_missing_iface_status,
)
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Affinity, CloudInitNoCloud, Interface, Metadata, Multus, Network
from libs.vm.vm import BaseVirtualMachine, add_volume_disk, cloudinitdisk_storage
from tests.network.libs import cloudinit
from tests.network.libs.cloudinit import primary_iface_cloud_init
from tests.network.libs.connectivity import ARP_ISOLATION_SYSCTL_CMD
from tests.network.utils import update_cloud_init_extra_user_data
from utilities import console
from utilities.constants.cluster import NODE_TYPE_WORKER_LABEL
from utilities.constants.components import KUBEMACPOOL_MAC_CONTROLLER_MANAGER
from utilities.constants.networking import LINUX_BRIDGE, SRIOV
from utilities.constants.timeouts import TIMEOUT_1MIN, TIMEOUT_2MIN, TIMEOUT_5SEC
from utilities.infra import get_pod_by_name_prefix
from utilities.jira import is_jira_open
from utilities.network import (
    cloud_init_network_data,
    compose_cloud_init_data_dict,
    network_device,
    ping,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, prepare_cloud_init_user_data, vm_console_run_commands

LOGGER = logging.getLogger(__name__)

LINUX_BRIDGE_IFACE_NAME_1: Final[str] = "linux-bridge-1"
LINUX_BRIDGE_IFACE_NAME_2: Final[str] = "linux-bridge-2"


NETWORK_MANAGER_UNMANAGE_RUNCMD = [
    'sudo echo -e "[main]\nno-auto-default=*\nignore-carrier=*" > /etc/NetworkManager/conf.d/no-nm-ownership.conf',
    "sudo systemctl restart NetworkManager",
]
IPV4_ADDRESS_SUBNET_PREFIX_LENGTH = 24
DHCP_INTERFACE_NAME = "eth3"


def _lookup_vmi_interface(vmi, interface_name):
    for interface in vmi.instance.spec.domain.devices.interfaces:
        if interface["name"] == interface_name:
            return interface

    return None


def wait_for_interface_hot_plug_completion(vmi, interface_name):
    try:
        for interface in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=TIMEOUT_5SEC,
            func=_lookup_vmi_interface,
            vmi=vmi,
            interface_name=interface_name,
        ):
            if interface is not None:
                return interface

    except TimeoutExpiredError:
        vmi_spec = vmi.instance.spec
        LOGGER.error(
            f"Hot-plugged interface {interface_name} not updated in VMI {vmi.name} spec.\n"
            f"VMI networks: {vmi_spec.networks}\n"
            f"VMI interface: {vmi_spec.domain.devices.interfaces}"
        )
        raise


def create_vm_with_secondary_interface_on_setup(
    namespace,
    client,
    bridge_nad,
    vm_name,
    ipv4_address_suffix,
):
    networks = {bridge_nad.name: bridge_nad.name}
    cloud_init_data = compose_cloud_init_data_dict(
        network_data={
            "ethernets": {
                "eth1": {
                    "addresses": [
                        f"{random_ipv4_address(net_seed=0, host_address=ipv4_address_suffix)}/{
                            IPV4_ADDRESS_SUBNET_PREFIX_LENGTH
                        }"
                    ]
                }
            }
        }
    )
    cloud_init_data["userData"] = {}
    update_cloud_init_extra_user_data(
        cloud_init_data=cloud_init_data["userData"],
        cloud_init_extra_user_data={"runcmd": NETWORK_MANAGER_UNMANAGE_RUNCMD},
    )

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        networks=networks,
        interfaces=networks.keys(),
        cloud_init_data=cloud_init_data,
        client=client,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


def hot_plug_interface(
    vm,
    hot_plugged_interface_name,
    net_attach_def_name,
    sriov=False,
):
    interface_type = SRIOV if sriov else "bridge"
    interfaces = vm.get_interfaces()
    interfaces.append({interface_type: {}, "name": hot_plugged_interface_name})
    networks = vm.instance.spec.template.spec.networks
    networks.append({
        "multus": {"networkName": net_attach_def_name},
        "name": hot_plugged_interface_name,
    })

    update_hot_plug_config_in_vm(vm=vm, interfaces=interfaces, networks=networks)

    try:
        return lookup_iface_status(
            vm=vm,
            iface_name=hot_plugged_interface_name,
            predicate=lambda interface: "guest-agent" in interface["infoSource"],
            timeout=TIMEOUT_2MIN,
        )
    except VMInterfaceStatusNotFoundError:
        if is_jira_open(jira_id="CNV-77961"):
            fallback_iface = _iface_console_fallback(vm=vm, interface_name=hot_plugged_interface_name)
            if fallback_iface:
                return fallback_iface
        raise


def hot_unplug_interface(vm, hot_plugged_interface_name):
    interfaces = vm.get_interfaces()
    unplugged_interface = next(interface for interface in interfaces if interface["name"] == hot_plugged_interface_name)
    unplugged_interface.update({"state": "absent"})

    update_hot_plug_config_in_vm(vm=vm, interfaces=interfaces)

    wait_for_missing_iface_status(vm=vm, iface_name=hot_plugged_interface_name)


def update_hot_plug_config_in_vm(vm, interfaces, networks=None):
    spec_dict = {
        "domain": {
            "devices": {
                "interfaces": interfaces,
            }
        },
    }

    if networks:
        spec_dict.update({"networks": networks})

    ResourceEditor(
        patches={
            vm: {
                "spec": {
                    "template": {
                        "spec": spec_dict,
                    }
                }
            }
        }
    ).update()


def create_bridge_interface_for_hot_plug(
    bridge_name,
    bridge_port,
    client,
    mtu=None,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"{bridge_name}-nncp",
        interface_name=bridge_name,
        ports=[bridge_port],
        ipv4_enable=True,
        ipv4_dhcp=True,
        node_selector_labels=NODE_TYPE_WORKER_LABEL,
        mtu=mtu,
        client=client,
    ) as br:
        yield br


def set_secondary_static_ip_address(
    vm: VirtualMachineForTests, ipv4_address: str, vmi_interface: str, guest_device_name: str | None = None
) -> None:
    guest_vm_interface = guest_device_name or get_guest_vm_interface_name_by_vmi_interface_name(
        vm=vm,
        vm_interface_name=vmi_interface,
    )
    console_command = f"sudo ip addr add {ipv4_address}/{IPV4_ADDRESS_SUBNET_PREFIX_LENGTH} dev {guest_vm_interface}"
    LOGGER.info(f"Sending command to {vm.name} console: '{console_command}'")
    with console.Console(vm=vm) as vm_console:
        vm_console.sendline(console_command)

    # Verify the IP address was set successfully.
    # The function fails on timeout if the interface or its address are not found,
    # so there's no need to check its return code.
    try:
        hot_plugged_interface_ip = lookup_iface_status_ip(vm=vm, iface_name=vmi_interface, ip_family=4)
    except IpNotFound:
        if is_jira_open(jira_id="CNV-77961"):
            hot_plugged_interface_ip = _read_guest_ipv4(vm=vm, interface_name=guest_vm_interface)
            LOGGER.warning(
                f"CNV-77961: Verified IP {hot_plugged_interface_ip} on {guest_vm_interface} via console "
                f"(guest-agent not reporting on VM {vm.name})."
            )
        else:
            raise
    LOGGER.info(f"{vm.name}/{vmi_interface} set with IP address {hot_plugged_interface_ip}")


def hot_plug_interface_and_set_address(
    vm,
    hot_plugged_interface_name,
    net_attach_def_name,
    ipv4_address,
    sriov=False,
):
    iface = hot_plug_interface(
        vm=vm,
        hot_plugged_interface_name=hot_plugged_interface_name,
        net_attach_def_name=net_attach_def_name,
        sriov=sriov,
    )

    set_secondary_static_ip_address(
        vm=vm,
        ipv4_address=ipv4_address,
        vmi_interface=iface.name,
        guest_device_name=iface.interfaceName,
    )

    return iface


def get_guest_vm_interface_name_by_vmi_interface_name(vm, vm_interface_name):
    vmi_interfaces = vm.vmi.interfaces
    for interface in vmi_interfaces:
        if interface["name"] == vm_interface_name and interface.get("interfaceName"):
            return interface["interfaceName"]

    if is_jira_open(jira_id="CNV-77961"):
        fallback = _iface_console_fallback(vm=vm, interface_name=vm_interface_name)
        if fallback:
            return fallback.interfaceName
    raise VMInterfaceStatusNotFoundError(f"Interface {vm_interface_name} not found in VM {vm.name} status")


def _iface_console_fallback(vm: VirtualMachine, interface_name: str) -> ResourceField | None:
    """Look up a hot-plugged interface via console when guest-agent is dead (CNV-77961).

    Args:
        vm: The virtual machine to query.
        interface_name: The spec-level interface name.

    Returns:
        A ResourceField with interface data gathered from the guest, or None.
    """
    # VMI spec interfaces are set by virt-controller seconds after the hot-plug request;
    # by the time we get here, lookup_iface_status has already waited 2 min for guest-agent.
    vmi_iface = _lookup_vmi_interface(vmi=vm.vmi, interface_name=interface_name)
    if not vmi_iface:
        return None
    LOGGER.warning(
        f"CNV-77961: Guest agent did not report interface {interface_name} on VM {vm.name}, "
        f"falling back to console lookup by MAC {vmi_iface['macAddress']}."
    )
    fallback = _lookup_guest_interface_by_mac(vm=vm, expected_mac=vmi_iface["macAddress"], iface_name=interface_name)
    LOGGER.info(f"Console fallback found interface {fallback.interfaceName} for {interface_name} on VM {vm.name}.")
    return fallback


def _lookup_guest_interface_by_mac(
    vm: VirtualMachine,
    expected_mac: str,
    iface_name: str,
) -> ResourceField:
    """Find an interface inside the VM guest OS by its MAC address.

    Used as a fallback when guest-agent fails to report the interface (CNV-77961).

    Args:
        vm: The virtual machine to query.
        expected_mac: The MAC address to search for.
        iface_name: The spec-level interface name to set on the returned object.

    Returns:
        A ResourceField with name and interfaceName fields.

    Raises:
        VMInterfaceStatusNotFoundError: If no interface with the expected MAC is found.
    """
    cmd = "ip -j addr show"
    output = vm_console_run_commands(vm=vm, commands=[cmd], timeout=30)
    guest_interfaces = json.loads(output[cmd][1])
    visible_ifaces = [{"ifname": iface.get("ifname"), "address": iface.get("address")} for iface in guest_interfaces]
    LOGGER.info(f"CNV-77961: looking for MAC {expected_mac} in guest {vm.name}, visible interfaces: {visible_ifaces}")
    for guest_iface in guest_interfaces:
        if guest_iface.get("address", "").lower() == expected_mac.lower():
            return ResourceField(
                params={
                    "name": iface_name,
                    "interfaceName": guest_iface["ifname"],
                }
            )

    raise VMInterfaceStatusNotFoundError(f"No interface with MAC {expected_mac} found inside VM {vm.name}")


def _read_guest_ipv4(vm: VirtualMachine, interface_name: str) -> ipaddress.IPv4Address:
    cmd = f"ip -j -4 addr show {interface_name}"
    output = vm_console_run_commands(vm=vm, commands=[cmd], timeout=30)
    iface_info = json.loads(output[cmd][1])
    if iface_info and "addr_info" in iface_info[0]:
        for addr in iface_info[0]["addr_info"]:
            if addr["family"] == "inet":
                return ipaddress.IPv4Address(address=addr["local"])
    raise IpNotFound(f"No IPv4 address found on {interface_name} in VM {vm.name}")


@contextlib.contextmanager
def create_vm_for_hot_plug(
    namespace_name,
    vm_name,
    client,
):
    cloud_init_data = {"userData": {}}
    update_cloud_init_extra_user_data(
        cloud_init_data=cloud_init_data["userData"],
        cloud_init_extra_user_data={"runcmd": NETWORK_MANAGER_UNMANAGE_RUNCMD},
    )

    with VirtualMachineForTests(
        namespace=namespace_name,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        client=client,
        cloud_init_data=cloud_init_data,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


def check_mac_released(
    kubemacpool_controller_log,
    interface_mac_address,
):
    if re.search(
        rf"(?=.*released [a ]*mac)(?=.*{interface_mac_address})",
        kubemacpool_controller_log,
        re.MULTILINE,
    ):
        return True


def search_hot_plugged_interface_in_vmi(vm, interface_name):
    try:
        return wait_for_interface_hot_plug_completion(vmi=vm.vmi, interface_name=interface_name)
    except TimeoutExpiredError:
        raise VMInterfaceStatusNotFoundError(f"Interface {interface_name} not found in VM {vm.name} status")


def get_kubemacpool_controller_log(
    client,
    namespace_name,
    log_start_time,
):
    kmp_controller_pod = get_pod_by_name_prefix(
        client=client,
        pod_prefix=KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
        namespace=namespace_name,
    )

    # Instead of getting the entire log of the kubemacpool-mac-controller-manager pod, get only the relevant part,
    # with an extra buffer of 10 seconds (to make sure no valid data was missed).
    required_log_duration = round(time.time() - log_start_time + 10)
    return kmp_controller_pod.log(container="manager", since_seconds=required_log_duration)


def get_primary_and_hot_plugged_mac_addresses(vm, hot_plugged_interface):
    primary_interface = vm.instance.spec.template.spec.domain.devices.interfaces[0]
    hot_plugged_interface_mac = search_hot_plugged_interface_in_vmi(
        vm=vm,
        interface_name=hot_plugged_interface,
    ).macAddress
    return [
        {primary_interface.name: primary_interface.macAddress},
        {hot_plugged_interface: hot_plugged_interface_mac},
    ]


def wait_for_no_packet_loss_after_connection(src_vm, dst_ip, interface=None):
    sleep_count_value = 10

    def _get_ping_state():
        return (
            ping(
                src_vm=src_vm,
                dst_ip=dst_ip,
                count=sleep_count_value,
                interface=interface,
            )
            == 0
        )

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=sleep_count_value,
            func=_get_ping_state,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Ping from {src_vm.name} to {dst_ip} failed.")
        raise


def secondary_network_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    nad_name: str,
    secondary_iface_name: str,
    secondary_iface_addresses: list[str],
    affinity: Affinity | None = None,
    labels: dict[str, str] | None = None,
) -> BaseVirtualMachine:
    """Create a Fedora VM with a masquerade primary interface and a secondary Linux bridge interface.

    Args:
        namespace: Namespace to deploy the VM in.
        name: VM name.
        client: Kubernetes dynamic client.
        nad_name: NetworkAttachmentDefinition name for the secondary interface.
        secondary_iface_name: Name of the secondary network interface in the VM spec.
        secondary_iface_addresses: CIDR addresses to assign to the secondary interface via cloud-init.
        affinity: Optional node or pod affinity rules for scheduling.
        labels: Optional labels to apply to the VM template metadata for pod scheduling.
    """
    spec = base_vmspec()
    spec.template.spec.domain.devices.interfaces = [  # type: ignore
        Interface(name="default", masquerade={}),
        Interface(name=secondary_iface_name, bridge={}),
    ]
    spec.template.spec.networks = [
        Network(name="default", pod={}),
        Network(name=secondary_iface_name, multus=Multus(networkName=nad_name)),
    ]
    if affinity:
        spec.template.spec.affinity = affinity

    if labels:
        spec.template.metadata = spec.template.metadata or Metadata()
        spec.template.metadata.labels = spec.template.metadata.labels or {}
        spec.template.metadata.labels.update(labels)

    ethernets = {}
    primary = primary_iface_cloud_init()
    if primary:
        ethernets["eth0"] = primary
    ethernets["eth1"] = cloudinit.EthernetDevice(addresses=secondary_iface_addresses)

    disk, volume = cloudinitdisk_storage(
        data=CloudInitNoCloud(
            networkData=cloudinit.asyaml(no_cloud=cloudinit.NetworkData(ethernets=ethernets)),
            userData=cloudinit.format_cloud_config(userdata=cloudinit.UserData(users=[])),
        )
    )
    spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=volume, disk=disk)
    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)


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
    client,
    dhcp_interface_config,
    cloud_init_extra_user_data=None,
    node_selector=None,
):
    cloud_init_data = _cloud_init_data(
        ip_addresses=ip_addresses,
        mpls_local_ip=mpls_local_ip,
        mpls_local_tag=mpls_local_tag,
        mpls_dest_ip=mpls_dest_ip,
        mpls_dest_tag=mpls_dest_tag,
        mpls_route_next_hop=mpls_route_next_hop,
        cloud_init_extra_user_data=cloud_init_extra_user_data,
        dhcp_interface_config=dhcp_interface_config,
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


def _cloud_init_data(
    ip_addresses,
    mpls_local_ip,
    mpls_local_tag,
    mpls_dest_ip,
    mpls_dest_tag,
    mpls_route_next_hop,
    cloud_init_extra_user_data,
    dhcp_interface_config,
):
    network_data_data = {
        "ethernets": {
            "eth1": {"addresses": [f"{ip_addresses[0]}/24"]},
            "eth2": {"addresses": [f"{ip_addresses[1]}/24"]},
            "eth4": {"addresses": [f"{ip_addresses[3]}/24"]},
            DHCP_INTERFACE_NAME: dhcp_interface_config,
        },
    }

    runcmd = [
        "modprobe mpls_router",  # In order to test mpls we need to load driver
        "sysctl -w net.mpls.platform_labels=1000",  # Activate mpls labeling feature
        "sysctl -w net.mpls.conf.eth4.input=1",  # Allow incoming mpls traffic
        *ARP_ISOLATION_SYSCTL_CMD,
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
        name: str,
        namespace: str,
        interfaces: list[str],
        ip_addresses: list[str],
        mpls_local_tag: int,
        mpls_local_ip: str,
        mpls_dest_ip: str,
        mpls_dest_tag: int,
        mpls_route_next_hop: str,
        client: DynamicClient,
        cloud_init_data: dict[str, dict] | None = None,
        node_selector: dict[str, str] | None = None,
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

        super().__init__(  # type: ignore[no-untyped-call]
            name=name,
            namespace=namespace,
            interfaces=interfaces,
            networks=networks,
            client=client,
            cloud_init_data=cloud_init_data,
            node_selector=node_selector,
        )

    def to_dict(self) -> None:
        self.body = fedora_vm_body(name=self.name)
        super().to_dict()  # type: ignore[no-untyped-call]
