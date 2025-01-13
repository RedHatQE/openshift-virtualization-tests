import pytest
from ocp_resources.virtual_machine import VirtualMachine

from utilities.constants import (
    ES_NONE,
    KMP_DISABLED_LABEL,
    KMP_VM_ASSIGNMENT_LABEL,
    LINUX_BRIDGE,
)
from utilities.infra import create_ns, get_node_selector_dict
from utilities.network import cloud_init, network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

NAD_MAC_SPOOF_NAME = "brspoofupgrade"


@pytest.fixture(scope="session")
def upgrade_linux_macspoof_nad(
    upgrade_namespace_scope_session,
):
    with network_nad(
        namespace=upgrade_namespace_scope_session,
        nad_type=LINUX_BRIDGE,
        nad_name=NAD_MAC_SPOOF_NAME,
        interface_name=NAD_MAC_SPOOF_NAME,
        macspoofchk=True,
        add_resource_name=False,
    ) as nad:
        yield nad


@pytest.fixture(scope="session")
def vm_nad_networks_data(upgrade_linux_macspoof_nad):
    return {upgrade_linux_macspoof_nad.name: upgrade_linux_macspoof_nad.name}


@pytest.fixture(scope="session")
def vma_upgrade_mac_spoof(worker_node1, unprivileged_client, upgrade_linux_macspoof_nad, vm_nad_networks_data):
    name = "vma-macspoof"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_linux_macspoof_nad.namespace,
        networks=vm_nad_networks_data,
        interfaces=sorted(vm_nad_networks_data.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.0.1"),
        body=fedora_vm_body(name=name),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        eviction_strategy=ES_NONE,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def vmb_upgrade_mac_spoof(worker_node1, unprivileged_client, upgrade_linux_macspoof_nad, vm_nad_networks_data):
    name = "vmb-macspoof"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_linux_macspoof_nad.namespace,
        networks=vm_nad_networks_data,
        interfaces=sorted(vm_nad_networks_data.keys()),
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.0.2"),
        body=fedora_vm_body(name=name),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        eviction_strategy=ES_NONE,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def running_vma_upgrade_mac_spoof(vma_upgrade_mac_spoof):
    return running_vm(vm=vma_upgrade_mac_spoof)


@pytest.fixture(scope="session")
def running_vmb_upgrade_mac_spoof(vmb_upgrade_mac_spoof):
    return running_vm(vm=vmb_upgrade_mac_spoof)


@pytest.fixture(scope="session")
def namespace_with_disabled_kmp():
    yield from create_ns(
        name="kmp-disabled-ns",
        labels={KMP_VM_ASSIGNMENT_LABEL: KMP_DISABLED_LABEL},
    )


@pytest.fixture(scope="session")
def running_vm_with_bridge(
    unprivileged_client,
    upgrade_namespace_scope_session,
    upgrade_br1test_nad,
):
    name = "vm-bridge-connected"
    with VirtualMachineForTests(
        name=name,
        namespace=upgrade_namespace_scope_session.name,
        networks={upgrade_br1test_nad.name: upgrade_br1test_nad.name},
        interfaces=[upgrade_br1test_nad.name],
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        eviction_strategy=ES_NONE,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm
