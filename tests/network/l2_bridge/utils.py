import contextlib
import logging
import re
import time

from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from libs.net.vmspec import lookup_iface_status, lookup_iface_status_ip, wait_for_missing_iface_status
from tests.network.libs.ip import random_ipv4_address
from tests.network.utils import update_cloud_init_extra_user_data
from utilities import console
from utilities.constants import (
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    LINUX_BRIDGE,
    NODE_TYPE_WORKER_LABEL,
    SRIOV,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
)
from utilities.infra import get_pod_by_name_prefix
from utilities.network import (
    IfaceNotFound,
    compose_cloud_init_data_dict,
    network_device,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body

LOGGER = logging.getLogger(__name__)

NETWORK_MANAGER_UNMANAGE_RUNCMD = [
    'sudo echo -e "[main]\nno-auto-default=*\nignore-carrier=*" > /etc/NetworkManager/conf.d/no-nm-ownership.conf',
    "sudo systemctl restart NetworkManager",
]
IPV4_ADDRESS_SUBNET_PREFIX_LENGTH = 24


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

    return lookup_iface_status(
        vm=vm,
        iface_name=hot_plugged_interface_name,
        predicate=lambda interface: "guest-agent" in interface["infoSource"],
        timeout=TIMEOUT_2MIN,
    )


def hot_unplug_interface(vm, hot_plugged_interface_name):
    interfaces = vm.get_interfaces()
    unplugged_interface = next(interface for interface in interfaces if interface["name"] == hot_plugged_interface_name)
    unplugged_interface.update(dict(state="absent"))

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


def set_secondary_static_ip_address(vm, ipv4_address, vmi_interface):
    guest_vm_interface = get_guest_vm_interface_name_by_vmi_interface_name(
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
    hot_plugged_interface_ip = lookup_iface_status_ip(vm=vm, iface_name=vmi_interface, ip_family=4)
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
    )

    return iface


def get_guest_vm_interface_name_by_vmi_interface_name(vm, vm_interface_name):
    vmi_interfaces = vm.vmi.interfaces
    for interface in vmi_interfaces:
        if interface["name"] == vm_interface_name:
            return interface["interfaceName"]
    raise IfaceNotFound(name=vm_interface_name)


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
        raise IfaceNotFound(name=interface_name)


def get_kubemacpool_controller_log(
    client,
    namespace_name,
    log_start_time,
):
    kmp_controller_pod = get_pod_by_name_prefix(
        dyn_client=client,
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


def create_vm_with_hot_plugged_sriov_interface(
    namespace_name,
    vm_name,
    sriov_network_for_hot_plug,
    ipv4_address,
    client,
):
    with create_vm_for_hot_plug(
        namespace_name=namespace_name,
        vm_name=vm_name,
        client=client,
    ) as vm:
        hot_plug_interface_and_set_address(
            vm=vm,
            hot_plugged_interface_name=sriov_network_for_hot_plug.name,
            net_attach_def_name=f"{namespace_name}/{sriov_network_for_hot_plug.name}",
            ipv4_address=ipv4_address,
            sriov=True,
        )
        yield vm
