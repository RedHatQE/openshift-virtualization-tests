import shlex

import pytest
from pyhelper_utils.shell import run_ssh_commands

from tests.network.jumbo_frame.utils import (
    cloud_init_data_for_secondary_traffic,
    create_vm_for_jumbo_test,
)
from utilities.constants import LINUX_BRIDGE, WORKER_NODE_LABEL_KEY
from utilities.infra import get_node_selector_dict
from utilities.network import get_vmi_ip_v4_by_name, network_device, network_nad
from utilities.virt import running_vm


@pytest.fixture(scope="class")
def running_vma_jumbo_primary_interface_worker_1(
    worker_node1,
    namespace,
    index_number,
    unprivileged_client,
):
    with create_vm_for_jumbo_test(
        index=next(index_number),
        namespace_name=namespace.name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def running_vmb_jumbo_primary_interface_worker_2(
    worker_node2,
    namespace,
    index_number,
    unprivileged_client,
):
    with create_vm_for_jumbo_test(
        index=next(index_number),
        namespace_name=namespace.name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def running_vmc_jumbo_primary_interface_worker_1(
    worker_node1,
    namespace,
    index_number,
    unprivileged_client,
):
    with create_vm_for_jumbo_test(
        index=next(index_number),
        namespace_name=namespace.name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def running_vmd_jumbo_primary_interface_and_secondary_interface(
    index_number,
    namespace,
    unprivileged_client,
    secondary_linux_bridge_nad,
):
    index = next(index_number)
    cloud_init_data = cloud_init_data_for_secondary_traffic(index=index)
    with create_vm_for_jumbo_test(
        index=index,
        namespace_name=namespace.name,
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
        networks={secondary_linux_bridge_nad.name: secondary_linux_bridge_nad.name},
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


@pytest.fixture()
def running_vme_jumbo_primary_interface_and_secondary_interface(
    index_number,
    namespace,
    unprivileged_client,
    secondary_linux_bridge_nad,
):
    index = next(index_number)
    cloud_init_data = cloud_init_data_for_secondary_traffic(index=index)
    with create_vm_for_jumbo_test(
        index=index,
        namespace_name=namespace.name,
        client=unprivileged_client,
        cloud_init_data=cloud_init_data,
        networks={secondary_linux_bridge_nad.name: secondary_linux_bridge_nad.name},
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


@pytest.fixture()
def secondary_linux_bridge_nad(namespace, linux_bridge_interface):
    with network_nad(
        namespace=namespace,
        nad_type=linux_bridge_interface.bridge_type,
        nad_name=f"{linux_bridge_interface.name}-nad",
        interface_name=linux_bridge_interface.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def linux_bridge_interface(hosts_common_available_ports):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="sec-br",
        interface_name="sec-br",
        ports=[hosts_common_available_ports[-1]],
        node_selector_labels={WORKER_NODE_LABEL_KEY: ""},
    ) as br:
        yield br


@pytest.fixture()
def ping_over_secondary(
    running_vmd_jumbo_primary_interface_and_secondary_interface,
    running_vme_jumbo_primary_interface_and_secondary_interface,
    secondary_linux_bridge_nad,
):
    dst_ip = get_vmi_ip_v4_by_name(
        vm=running_vmd_jumbo_primary_interface_and_secondary_interface,
        name=secondary_linux_bridge_nad.name,
    )

    run_ssh_commands(
        host=running_vme_jumbo_primary_interface_and_secondary_interface.ssh_exec,
        commands=[shlex.split(f"ping {dst_ip}  >& /dev/null &")],
    )
