from typing import TYPE_CHECKING

from libs.net.ip import filter_link_local_addresses
from libs.net.vmspec import lookup_iface_status, lookup_primary_network
from tests.network.libs.connectivity import build_ping_command, packet_loss_percent_from_ping_output

if TYPE_CHECKING:
    from pytest_subtests import SubTests

    from libs.vm.vm import BaseVirtualMachine


def assert_label_in_namespace(labeled_namespace, label_key, expected_label_value):
    namespace_labels = labeled_namespace.labels
    assert namespace_labels[label_key] == expected_label_value, (
        f"Namespace {labeled_namespace.name} should have label {label_key} "
        f"set to {expected_label_value}. Actual labels:\n{labeled_namespace.labels}."
    )


def assert_udn_vms_ping_connectivity(
    running_udn_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
    subtests: SubTests,
) -> None:
    """Assert ping connectivity between two UDN VMs over their primary network, per supported IP family.

    Iterates the destination VM's primary-network addresses so a dual-stack cluster is checked over
    both IPv4 and IPv6, while a single-stack cluster is checked over its single family.
    """
    source_vm, destination_vm = running_udn_vms
    destination_primary_iface_name = lookup_primary_network(vm=destination_vm).name
    iface_status = lookup_iface_status(vm=destination_vm, iface_name=destination_primary_iface_name)
    for destination_ip in filter_link_local_addresses(ip_addresses=iface_status.ipAddresses):
        with subtests.test(msg=f"IPv{destination_ip.version}"):
            ping_command = build_ping_command(dst_ip=str(destination_ip), count=3, timeout=10)
            ping_output = "\n".join(source_vm.console(commands=[ping_command], timeout=30)[ping_command])
            assert packet_loss_percent_from_ping_output(ping_output=ping_output) == 0, (
                f"Ping from {source_vm.name} to {destination_ip} did not report 0% packet loss: {ping_output}"
            )
