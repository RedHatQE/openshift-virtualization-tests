"""
VM to VM connectivity
"""

import pytest

from utilities.constants import IPV4_STR, IPV6_STR
from utilities.infra import get_node_selector_dict
from utilities.network import (
    compose_cloud_init_data_dict,
    get_ip_from_vm_or_virt_handler_pod,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm, vm_console_run_commands


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
    return running_vm(vm=pod_net_vma, wait_for_cloud_init=True)


@pytest.fixture()
def pod_net_running_vmb(pod_net_vmb):
    return running_vm(vm=pod_net_vmb, wait_for_cloud_init=True)


@pytest.fixture(scope="module")
def cloud_init_ipv6_network_data(dual_stack_network_data):
    return compose_cloud_init_data_dict(ipv6_network_data=dual_stack_network_data)


@pytest.mark.parametrize(
    "ip_family",
    [
        pytest.param(
            IPV4_STR,
            marks=[
                pytest.mark.polarion("CNV-2332"),
                pytest.mark.ipv4,
            ],
        ),
        pytest.param(
            IPV6_STR,
            marks=[
                pytest.mark.polarion("CNV-11845"),
                pytest.mark.ipv6,
                pytest.mark.jira("CNV-58529", run=True),
            ],
        ),
    ],
    indirect=False,
)
@pytest.mark.gating
def test_connectivity_over_pod_network(
    ip_family,
    pod_net_vma,
    pod_net_vmb,
    pod_net_running_vma,
    pod_net_running_vmb,
    namespace,
):
    """
    Check connectivity
    """
    dst_ip = get_ip_from_vm_or_virt_handler_pod(family=ip_family, vm=pod_net_running_vmb)
    assert dst_ip, f"Cannot get valid IP address from {pod_net_running_vmb.vmi.name}."

    ping_cmd = f"ping -c 3 {dst_ip}"
    vm_console_run_commands(vm=pod_net_running_vma, commands=[ping_cmd])
