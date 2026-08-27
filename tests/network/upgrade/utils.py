from libs.net.vmspec import lookup_iface_status_ip, lookup_primary_network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.connectivity import build_ping_command, packet_loss_percent_from_ping_output
from utilities.virt import vm_console_run_commands


def assert_label_in_namespace(labeled_namespace, label_key, expected_label_value):
    namespace_labels = labeled_namespace.labels
    assert namespace_labels[label_key] == expected_label_value, (
        f"Namespace {labeled_namespace.name} should have label {label_key} "
        f"set to {expected_label_value}. Actual labels:\n{labeled_namespace.labels}."
    )


def measure_udn_vms_ipv4_packet_loss(
    running_udn_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> float:
    """Ping from one UDN VM to the other over their primary network IPv4 address and report packet loss.

    The ping return code is ignored so its output can be parsed for the actual loss percentage.

    Args:
        running_udn_vms: The source and destination VMs, each attached to the primary UDN network.

    Returns:
        The packet-loss percentage (0-100) measured over IPv4.
    """
    source_vm, destination_vm = running_udn_vms
    destination_ip = lookup_iface_status_ip(
        vm=destination_vm,
        iface_name=lookup_primary_network(vm=destination_vm).name,
        ip_family=4,
    )
    ping_command = build_ping_command(dst_ip=str(destination_ip), count=3, timeout=10)
    output = vm_console_run_commands(
        vm=source_vm,
        commands=[ping_command],
        timeout=15,
        return_code_validation=False,
    )
    return packet_loss_percent_from_ping_output(ping_output="\n".join(output[ping_command]))
