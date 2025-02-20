import pytest
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.resource import ResourceEditor

from utilities.constants import KMP_VM_ASSIGNMENT_LABEL, LINUX_BRIDGE
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import create_ns, get_node_selector_dict, name_prefix
from utilities.network import network_device, network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

from . import utils as kmp_utils


@pytest.fixture(scope="module")
def kubemacpool_bridge_device_name(index_number):
    yield f"br{next(index_number)}test"


@pytest.fixture(scope="module")
def kubemacpool_bridge_device_worker_1(
    worker_node1,
    kubemacpool_bridge_device_name,
    nodes_available_nics,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"kubemacpool-{name_prefix(worker_node1.name)}",
        interface_name=kubemacpool_bridge_device_name,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.name][-1]],
    ) as dev:
        yield dev


@pytest.fixture(scope="module")
def kubemacpool_bridge_device_worker_2(
    worker_node2,
    kubemacpool_bridge_device_name,
    nodes_available_nics,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"kubemacpool-{name_prefix(worker_node2.name)}",
        interface_name=kubemacpool_bridge_device_name,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[nodes_available_nics[worker_node2.name][-1]],
    ) as dev:
        yield dev


@pytest.fixture(scope="module")
def manual_mac_nad(
    namespace,
    kubemacpool_bridge_device_worker_1,
    kubemacpool_bridge_device_worker_2,
    kubemacpool_bridge_device_name,
):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=f"{kubemacpool_bridge_device_name}-manual-mac-nad",
        interface_name=kubemacpool_bridge_device_name,
        namespace=namespace,
    ) as manual_mac_nad:
        yield manual_mac_nad


@pytest.fixture(scope="module")
def automatic_mac_nad(
    namespace,
    kubemacpool_bridge_device_worker_1,
    kubemacpool_bridge_device_worker_2,
    kubemacpool_bridge_device_name,
):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=f"{kubemacpool_bridge_device_name}-automatic-mac-nad",
        interface_name=kubemacpool_bridge_device_name,
        namespace=namespace,
    ) as automatic_mac_nad:
        yield automatic_mac_nad


@pytest.fixture(scope="module")
def manual_mac_out_of_pool_nad(
    namespace,
    kubemacpool_bridge_device_worker_1,
    kubemacpool_bridge_device_worker_2,
    kubemacpool_bridge_device_name,
):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=f"{kubemacpool_bridge_device_name}-manual-out-pool-mac-nad",
        interface_name=kubemacpool_bridge_device_name,
        namespace=namespace,
    ) as manual_mac_out_pool_nad:
        yield manual_mac_out_pool_nad


@pytest.fixture(scope="module")
def automatic_mac_tuning_net_nad(
    namespace,
    kubemacpool_bridge_device_worker_1,
    kubemacpool_bridge_device_worker_2,
    kubemacpool_bridge_device_name,
):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=f"{kubemacpool_bridge_device_name}-automatic-mac-tun-net-nad",
        interface_name=kubemacpool_bridge_device_name,
        namespace=namespace,
    ) as automatic_mac_tuning_net_nad:
        yield automatic_mac_tuning_net_nad


@pytest.fixture(scope="class")
def disabled_ns_nad(
    disabled_ns,
    kubemacpool_bridge_device_worker_1,
    kubemacpool_bridge_device_worker_2,
    kubemacpool_bridge_device_name,
):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=f"{kubemacpool_bridge_device_name}-{disabled_ns.name}-nad",
        interface_name=kubemacpool_bridge_device_name,
        namespace=disabled_ns,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def enabled_ns_nad(
    kmp_enabled_ns,
    kubemacpool_bridge_device_worker_1,
    kubemacpool_bridge_device_worker_2,
    kubemacpool_bridge_device_name,
):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=f"{kubemacpool_bridge_device_name}-{kmp_enabled_ns.name}-nad",
        interface_name=kubemacpool_bridge_device_name,
        namespace=kmp_enabled_ns,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def no_label_ns_nad(
    no_label_ns,
    kubemacpool_bridge_device_worker_1,
    kubemacpool_bridge_device_worker_2,
    kubemacpool_bridge_device_name,
):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=f"{kubemacpool_bridge_device_name}-{no_label_ns.name}-nad",
        interface_name=kubemacpool_bridge_device_name,
        namespace=no_label_ns,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def all_nads(
    manual_mac_nad,
    automatic_mac_nad,
    manual_mac_out_of_pool_nad,
    automatic_mac_tuning_net_nad,
):
    return [
        manual_mac_nad.name,
        automatic_mac_nad.name,
        manual_mac_out_of_pool_nad.name,
        automatic_mac_tuning_net_nad.name,
    ]


@pytest.fixture(scope="class")
def vm_a(
    namespace,
    all_nads,
    worker_node1,
    kubemacpool_bridge_device_worker_1,
    mac_pool,
    unprivileged_client,
):
    requested_network_config = kmp_utils.vm_network_config(
        mac_pool=mac_pool, all_nads=all_nads, end_ip_octet=1, mac_uid="1"
    )
    yield from kmp_utils.create_vm(
        name="vm-fedora-a",
        iface_config=requested_network_config,
        namespace=namespace,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        client=unprivileged_client,
        mac_pool=mac_pool,
    )


@pytest.fixture(scope="class")
def vm_b(
    namespace,
    all_nads,
    worker_node2,
    kubemacpool_bridge_device_worker_2,
    mac_pool,
    unprivileged_client,
):
    requested_network_config = kmp_utils.vm_network_config(
        mac_pool=mac_pool, all_nads=all_nads, end_ip_octet=2, mac_uid="2"
    )
    yield from kmp_utils.create_vm(
        name="vm-fedora-b",
        iface_config=requested_network_config,
        namespace=namespace,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        client=unprivileged_client,
        mac_pool=mac_pool,
    )


@pytest.fixture(scope="class")
def running_vm_a(vm_a):
    return running_vm(vm=vm_a, wait_for_cloud_init=True)


@pytest.fixture(scope="class")
def running_vm_b(vm_b):
    return running_vm(vm=vm_b, wait_for_cloud_init=True)


@pytest.fixture(scope="function")
def restarted_vmi_a(vm_a):
    vm_a.stop(wait=True)
    return running_vm(vm=vm_a, wait_for_cloud_init=True)


@pytest.fixture(scope="function")
def restarted_vmi_b(vm_b):
    vm_b.stop(wait=True)
    return running_vm(vm=vm_b, wait_for_cloud_init=True)


@pytest.fixture(scope="class")
def disabled_ns_vm(disabled_ns, disabled_ns_nad, mac_pool):
    networks = {disabled_ns_nad.name: disabled_ns_nad.name}
    name = f"{disabled_ns.name}-vm"
    with VirtualMachineForTests(
        namespace=disabled_ns.name,
        name=name,
        networks=networks,
        interfaces=networks.keys(),
        body=fedora_vm_body(name=name),
    ) as vm:
        mac_pool.append_macs(vm=vm)
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm
        mac_pool.remove_macs(vm=vm)


@pytest.fixture(scope="class")
def enabled_ns_vm(kmp_enabled_ns, enabled_ns_nad, mac_pool):
    networks = {enabled_ns_nad.name: enabled_ns_nad.name}
    name = f"{kmp_enabled_ns.name}-vm"
    with VirtualMachineForTests(
        namespace=kmp_enabled_ns.name,
        name=name,
        networks=networks,
        interfaces=networks.keys(),
        body=fedora_vm_body(name=name),
    ) as vm:
        mac_pool.append_macs(vm=vm)
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm
        mac_pool.remove_macs(vm=vm)


@pytest.fixture(scope="class")
def no_label_ns_vm(no_label_ns, no_label_ns_nad, mac_pool):
    networks = {no_label_ns_nad.name: no_label_ns_nad.name}
    name = f"{no_label_ns.name}-vm"
    with VirtualMachineForTests(
        namespace=no_label_ns.name,
        name=name,
        networks=networks,
        interfaces=networks.keys(),
        body=fedora_vm_body(name=name),
    ) as vm:
        mac_pool.append_macs(vm=vm)
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm
        mac_pool.remove_macs(vm=vm)


@pytest.fixture(scope="class")
def disabled_ns(kmp_vm_label):
    kmp_vm_label[KMP_VM_ASSIGNMENT_LABEL] = "ignore"
    yield from create_ns(name="kmp-disabled", labels=kmp_vm_label)


@pytest.fixture(scope="class")
def no_label_ns(kmp_vm_label):
    yield from create_ns(name="kmp-default")


@pytest.fixture()
def kmp_down(cnao_down, kmp_deployment):
    with ResourceEditor(patches={kmp_deployment: {"spec": {"replicas": 0}}}):
        kmp_deployment.wait_for_replicas(deployed=False)
        yield

    kmp_deployment.wait_for_replicas()


@pytest.fixture()
def cnao_down(cnao_deployment):
    with ResourceEditorValidateHCOReconcile(
        patches={cnao_deployment: {"spec": {"replicas": 0}}},
        list_resource_reconcile=[NetworkAddonsConfig],
    ):
        cnao_deployment.wait_for_replicas(deployed=False)
        yield

    cnao_deployment.wait_for_replicas()
