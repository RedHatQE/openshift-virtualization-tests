import logging

import pytest
from ocp_utilities.exceptions import CommandExecFailed

from utilities.infra import ExecCommandOnPod, get_node_selector_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def ovs_bond_vma(schedulable_nodes, namespace, unprivileged_client, node_with_bond):
    name = "vma"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=get_node_selector_dict(node_selector=node_with_bond),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def ovs_bond_vmb(schedulable_nodes, namespace, unprivileged_client, node_with_bond):
    name = "vmb"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=get_node_selector_dict(
            node_selector=next(filter(lambda node: node.name != node_with_bond, schedulable_nodes)).hostname
        ),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="module")
def running_ovs_bond_vma(ovs_bond_vma):
    return running_vm(vm=ovs_bond_vma)


@pytest.fixture(scope="module")
def running_ovs_bond_vmb(ovs_bond_vmb):
    return running_vm(vm=ovs_bond_vma)


def get_interface_by_attribute(all_connections, att):
    connection_array = all_connections.split("\n")
    if att in connection_array:
        iface_name_string = connection_array[connection_array.index(att) - 1]
        iface_name = iface_name_string.split(":")[1]
        return iface_name


@pytest.fixture(scope="module")
def bond_and_privileged_pod(workers_utility_pods):
    """
    Get OVS BOND from the worker, if OVS BOND not exists the tests should be skipped.
    """
    skip_msg = "BOND is not configured on the workers on primary interface"
    for pod in workers_utility_pods:
        pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=pod.node)
        try:
            # TODO: use rrmngmnt to get info from nmcli
            all_connections = _all_connection(pod_exec=pod_exec)
            bond = get_interface_by_attribute(all_connections=all_connections[0], att="ovs-port.bond-mode:balance-slb")

            if bond:
                return bond, pod

            pytest.skip(skip_msg)
        except CommandExecFailed:
            pytest.skip(skip_msg)
            break


@pytest.fixture(scope="module")
def privileged_pod(bond_and_privileged_pod):
    _, pod = bond_and_privileged_pod
    return pod


@pytest.fixture(scope="module")
def bond(bond_and_privileged_pod):
    bond, _ = bond_and_privileged_pod
    return bond


@pytest.fixture(scope="module")
def node_with_bond(privileged_pod):
    return privileged_pod.node.hostname


@pytest.fixture(scope="module")
def bond_port(workers_utility_pods, privileged_pod, bond, node_with_bond):
    pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=node_with_bond)
    all_connections = _all_connection(pod_exec=pod_exec)

    bond_string = f"connection.master:{bond}"
    bond_port = get_interface_by_attribute(all_connections=all_connections, att=bond_string)

    assert bond_port is not None, f"OVS Bond {bond} on node {node_with_bond} has no ports"
    return bond_port


@pytest.fixture(scope="module")
def skip_when_no_bond(bond):
    if not bond:
        pytest.skip("The test requires at least one node with an OVS bond")


@pytest.fixture(scope="module")
def disconnected_bond_port(privileged_pod, bond_port, bond):
    LOGGER.info(f"Disconnecting port {bond_port} of bond {bond}")
    privileged_pod.execute(command=["bash", "-c", f"nmcli dev disconnect {bond_port}"])

    yield bond_port

    LOGGER.info(f"Reconnecting port {bond_port} of bond {bond}")
    privileged_pod.execute(command=["bash", "-c", f"nmcli dev connect {bond_port}"])


def _all_connection(pod_exec):
    return pod_exec.exec(
        command=(
            "nmcli -g name con show | xargs -i nmcli -t -f "
            'connection.interface-name,ovs-port.bond-mode connection show "{}"'
        )
    )
