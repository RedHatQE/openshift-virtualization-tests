import logging
from contextlib import contextmanager

import pytest
from kubernetes.client import ApiException

from utilities.network import LINUX_BRIDGE, network_device, network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body

LOGGER = logging.getLogger(__name__)


MAC_ADDRESS = "macAddress"


@contextmanager
def create_dry_run_vm(name, namespace, networks, unprivileged_client, macs=None):
    vm = VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        macs=macs,
        dry_run="All",
    )
    yield vm

    if vm.exists:
        vm.clean_up()


@pytest.fixture()
def bridge_on_all_nodes():
    bridge_name = "br-dry-run-test"
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"{bridge_name}-nncp",
        interface_name=bridge_name,
    ) as dev:
        yield dev


@pytest.fixture()
def linux_bridge_network_nad(namespace, bridge_on_all_nodes):
    with network_nad(
        nad_type=bridge_on_all_nodes.bridge_type,
        nad_name=f"{bridge_on_all_nodes.bridge_name}-nad",
        interface_name=bridge_on_all_nodes.bridge_name,
        namespace=namespace,
    ) as dry_run_nad:
        yield dry_run_nad


@pytest.fixture()
def dry_run_vma(unprivileged_client, namespace, linux_bridge_network_nad):
    with create_dry_run_vm(
        name="dry-run-vma",
        namespace=namespace,
        networks={linux_bridge_network_nad.name: linux_bridge_network_nad.name},
        unprivileged_client=unprivileged_client,
    ) as vm:
        yield vm.create()


@pytest.fixture()
def dry_run_vma_mac_address(dry_run_vma):
    vm_mac_address = dry_run_vma.spec.template.spec.domain.devices.interfaces[1][MAC_ADDRESS]
    # dry-run VM's have only "spec" or "metadata" attributes
    LOGGER.info(f"Allocated MAC address {vm_mac_address} for {dry_run_vma.metadata.name}")
    return vm_mac_address


@pytest.fixture()
def vm_with_mac_address(
    unprivileged_client,
    namespace,
    linux_bridge_network_nad,
    dry_run_vma_mac_address,
):
    """Create a VM with a MAC address retrieved from a VM created in dry-run mode."""
    networks = {linux_bridge_network_nad.name: linux_bridge_network_nad.name}
    name = "vm-with-mac"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        macs={linux_bridge_network_nad.name: dry_run_vma_mac_address},
    ) as vm:
        yield vm


@pytest.fixture()
def dry_run_vm_with_mac_address(
    unprivileged_client,
    namespace,
    linux_bridge_network_nad,
    vm_with_mac_address,
):
    """Create a dry-run VM with a MAC address retrieved from a running VM."""
    allocated_mac_address = vm_with_mac_address.get_interfaces()[1][MAC_ADDRESS]

    return create_dry_run_vm(
        name="dry-run-vm-with-mac",
        namespace=namespace,
        networks={linux_bridge_network_nad.name: linux_bridge_network_nad.name},
        unprivileged_client=unprivileged_client,
        macs={linux_bridge_network_nad.name: allocated_mac_address},
    )


@pytest.mark.polarion("CNV-7872")
@pytest.mark.s390x
def test_dry_run_mac_not_saved(
    dry_run_vma_mac_address,
    vm_with_mac_address,
):
    """Assure that the MAC address given to a VM created in dry-run mode is still available in the MAC-pool."""
    vm_interfaces = vm_with_mac_address.get_interfaces()
    secondary_net_mac = vm_interfaces[1][MAC_ADDRESS]
    assert dry_run_vma_mac_address == secondary_net_mac, (
        f"{vm_with_mac_address.name} MAC address is {secondary_net_mac}"
        f" and not {dry_run_vma_mac_address}, as it should be."
    )


@pytest.mark.polarion("CNV-7873")
@pytest.mark.s390x
def test_allocated_mac_is_unavailable_for_dry_run(dry_run_vm_with_mac_address):
    with pytest.raises(ApiException, match="Failed to allocate mac to the vm object"):
        with dry_run_vm_with_mac_address as vm:
            vm.create()
