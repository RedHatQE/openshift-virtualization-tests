"""
VM to VM connectivity
"""

import pytest

from libs.net.vmspec import lookup_iface_status
from tests.network.libs.connectivity import build_ping_command
from utilities.infra import get_node_selector_dict
from utilities.network import (
    compose_cloud_init_data_dict,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, vm_console_run_commands


@pytest.fixture()
def pod_net_vma(
    namespace,
    unprivileged_client,
    nic_models_matrix__module__,
    cloud_init_ipv6_network_data,
    schedulable_nodes,
):
    node_selector = None if len(schedulable_nodes) < 2 else schedulable_nodes[0].hostname
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=get_node_selector_dict(node_selector=node_selector),
        client=unprivileged_client,
        network_model=nic_models_matrix__module__,
        body=fedora_vm_body(name=name),
        cloud_init_data=cloud_init_ipv6_network_data,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def pod_net_vmb(
    namespace,
    unprivileged_client,
    nic_models_matrix__module__,
    cloud_init_ipv6_network_data,
    schedulable_nodes,
):
    node_selector = None if len(schedulable_nodes) < 2 else schedulable_nodes[1].hostname
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=get_node_selector_dict(node_selector=node_selector),
        client=unprivileged_client,
        network_model=nic_models_matrix__module__,
        body=fedora_vm_body(name=name),
        cloud_init_data=cloud_init_ipv6_network_data,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture()
def pod_net_running_vma(pod_net_vma):
    pod_net_vma.wait_for_agent_connected()
    return pod_net_vma


@pytest.fixture()
def pod_net_running_vmb(pod_net_vmb):
    pod_net_vmb.wait_for_agent_connected()
    return pod_net_vmb


@pytest.fixture(scope="module")
def cloud_init_ipv6_network_data(ipv6_primary_interface_cloud_init_data):
    return compose_cloud_init_data_dict(ipv6_network_data=ipv6_primary_interface_cloud_init_data)


@pytest.mark.polarion("CNV-11845")
@pytest.mark.gating
@pytest.mark.single_nic
@pytest.mark.s390x
# conformance candidate
def test_connectivity_over_pod_network(
    subtests,
    pod_net_vma,
    pod_net_vmb,
    pod_net_running_vma,
    pod_net_running_vmb,
    namespace,
):
    """
    Check connectivity
    """
    target_vm_iface_name = pod_net_running_vmb.vmi.interfaces[0].name
    target_vm_ip_addresses = lookup_iface_status(vm=pod_net_running_vmb, iface_name=target_vm_iface_name)["ipAddresses"]
    for target_vm_ip in target_vm_ip_addresses:
        with subtests.test(msg=f"Testing connectivity to {target_vm_ip}"):
            ping_cmd = build_ping_command(dst_ip=target_vm_ip, count=3, timeout=10)
            vm_console_run_commands(vm=pod_net_running_vma, commands=[ping_cmd])
