from collections import OrderedDict

from utilities.constants import IPV6_STR
from utilities.network import (
    compose_cloud_init_data_dict,
    get_ip_from_vm_or_virt_handler_pod,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm, vm_console_run_commands


def create_running_vm(
    name,
    end_ip_octet,
    node_selector,
    network_names,
    dual_stack_network_data,
    client,
    namespace,
):
    networks = OrderedDict()

    for network_name in network_names:
        networks[network_name] = network_name

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=node_selector,
        cloud_init_data=compose_cloud_init_data_dict(
            network_data={
                "ethernets": {f"eth{i + 1}": {"addresses": [f"10.200.{i}.{end_ip_octet}/24"]} for i in range(0, 3)}
            },
            ipv6_network_data=dual_stack_network_data,
        ),
        client=client,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


def is_masquerade(vm, bridge):
    return (
        True
        if [
            interface
            for interface in vm.vmi.instance.spec.domain.devices.interfaces
            if interface["name"] == bridge and "masquerade" in interface.keys()
        ]
        else False
    )


def get_masquerade_vm_ip(vm, ipv6_testing):
    if ipv6_testing:
        return get_ip_from_vm_or_virt_handler_pod(family=IPV6_STR, vm=vm)
    return vm.vmi.virt_launcher_pod.instance.status.podIP


def verify_vm_connectivity_over_pod_network(ip_family, src_vm, dst_vm):
    dst_ip = get_ip_from_vm_or_virt_handler_pod(family=ip_family, vm=dst_vm)
    assert dst_ip, f"Cannot get valid {ip_family} address from {dst_vm.vmi.name}."

    ping_cmd = f"ping -c 3 {dst_ip}"
    vm_console_run_commands(vm=src_vm, commands=[ping_cmd])
