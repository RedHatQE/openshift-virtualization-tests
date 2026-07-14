"""
PCI Topology Stability Tests

STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/pci-topology-stability.md
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from ocp_resources.template import Template
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS
from tests.virt.utils import get_pci_fingerprint
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
)

if TYPE_CHECKING:
    from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)

pytestmark = [pytest.mark.rwx_default_storage, pytest.mark.data_collector_scope(scope="module")]


@pytest.fixture(scope="class")
def pci_topology_vm(
    request,
    namespace,
    unprivileged_client,
    golden_image_data_volume_template_for_test_scope_class,
    modern_cpu_for_migration,
):
    with VirtualMachineForTestsFromTemplate(
        name=request.param["vm_name"],
        labels=Template.generate_template_labels(**request.param["template_labels"]),
        namespace=namespace.name,
        client=unprivileged_client,
        data_volume_template=golden_image_data_volume_template_for_test_scope_class,
        cpu_model=modern_cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def initial_pci_fingerprint(pci_topology_vm):
    return get_pci_fingerprint(vm=pci_topology_vm)


@pytest.fixture()
def restarted_pci_topology_vm(pci_topology_vm, initial_pci_fingerprint):
    restart_vm_wait_for_running_vm(vm=pci_topology_vm)
    return pci_topology_vm


@pytest.fixture()
def migrated_pci_topology_vm(admin_client, pci_topology_vm, initial_pci_fingerprint):
    migrate_vm_and_verify(vm=pci_topology_vm, client=admin_client, check_ssh_connectivity=True)
    return pci_topology_vm


@pytest.fixture()
def snapshot_restored_pci_topology_vm(admin_client, pci_topology_vm, initial_pci_fingerprint):
    with VirtualMachineSnapshot(
        name=f"{pci_topology_vm.name}-snapshot",
        namespace=pci_topology_vm.namespace,
        vm_name=pci_topology_vm.name,
    ) as snapshot:
        snapshot.wait_snapshot_done()
        pci_topology_vm.stop(wait=True)
        LOGGER.info(f"Restoring VM {pci_topology_vm.name} from snapshot {snapshot.name}")
        with VirtualMachineRestore(
            client=admin_client,
            name=f"{pci_topology_vm.name}-restore",
            namespace=pci_topology_vm.namespace,
            vm_name=pci_topology_vm.name,
            snapshot_name=snapshot.name,
        ) as restore:
            restore.wait_restore_done()
    running_vm(vm=pci_topology_vm)
    return pci_topology_vm


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class, pci_topology_vm",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {"template_labels": RHEL_LATEST_LABELS, "vm_name": "pci-topology-vm"},
        ),
    ],
    indirect=True,
)
class TestPCITopologyStability:
    """
    Verify PCI device addresses remain stable across VM lifecycle operations.

    Preconditions:
        - RHEL VM created from latest template with a modern CPU model for migration,
          started and running with SSH access
        - PCI fingerprint (MD5 of sorted guest PCI BDF addresses) captured before each operation
    """

    @pytest.mark.polarion("CNV-16326")
    def test_pci_address_stability_on_restart(
        self,
        initial_pci_fingerprint: str,
        restarted_pci_topology_vm: VirtualMachineForTests,
    ):
        """
        Steps:
            1. Restart the VM and wait until it is running with SSH access
            2. Capture PCI fingerprint from the guest

        Expected:
            - Fingerprints match (PCI topology unchanged)
        """
        fingerprint_after = get_pci_fingerprint(vm=restarted_pci_topology_vm)
        assert fingerprint_after == initial_pci_fingerprint, (
            f"PCI topology changed after restart: before={initial_pci_fingerprint}, after={fingerprint_after}"
        )

    @pytest.mark.polarion("CNV-16327")
    def test_pci_address_stability_on_migration(
        self,
        initial_pci_fingerprint: str,
        migrated_pci_topology_vm: VirtualMachineForTests,
    ):
        """
        Steps:
            1. Live-migrate the VM and verify SSH connectivity
            2. Capture PCI fingerprint from the guest

        Expected:
            - Fingerprints match (PCI topology unchanged)
        """
        fingerprint_after = get_pci_fingerprint(vm=migrated_pci_topology_vm)
        assert fingerprint_after == initial_pci_fingerprint, (
            f"PCI topology changed after migration: before={initial_pci_fingerprint}, after={fingerprint_after}"
        )

    @pytest.mark.polarion("CNV-16328")
    @pytest.mark.usefixtures("skip_if_no_storage_class_for_snapshot")
    def test_pci_address_stability_on_snapshot_restore(
        self,
        initial_pci_fingerprint: str,
        snapshot_restored_pci_topology_vm: VirtualMachineForTests,
    ):
        """
        Preconditions:
            - Storage class supports snapshots

        Steps:
            1. Create a VM snapshot and wait until it completes
            2. Stop the VM
            3. Restore the VM from the snapshot
            4. Start the VM and wait until it is running with SSH access
            5. Capture PCI fingerprint from the guest

        Expected:
            - Fingerprints match (PCI topology unchanged)
        """
        fingerprint_after = get_pci_fingerprint(vm=snapshot_restored_pci_topology_vm)
        assert fingerprint_after == initial_pci_fingerprint, (
            f"PCI topology changed after snapshot restore: before={initial_pci_fingerprint}, after={fingerprint_after}"
        )
