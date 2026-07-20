"""
Live Migration Between RHCOS 9 and RHCOS 10 Worker Nodes

STP:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/dual-stream-cluster-rhcos9-rhcos10/stp.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, WINDOWS_LATEST, WINDOWS_LATEST_LABELS
from tests.virt.cluster.migration_and_maintenance.rhel9_rhel10_cluster.utils import (
    RHCOS9_AFFINITY,
    RHCOS10_AFFINITY,
    set_vm_affinity,
)
from tests.virt.utils import verify_guest_boot_time
from utilities.constants.cluster import RHCOS9_WORKER_LABEL
from utilities.virt import VirtualMachineForTests, get_vm_boot_time, migrate_vm_and_verify

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

pytestmark = [
    pytest.mark.mixed_os_nodes,
    pytest.mark.rwx_default_storage,
]


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_function, dual_stream_migration_vm",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {
                "vm_name": "migrate-rhcos10-to-rhcos9-rhel",
                "template_labels": RHEL_LATEST_LABELS,
                "vm_affinity": RHCOS10_AFFINITY,
            },
            marks=pytest.mark.polarion("CNV-16274"),
            id="RHEL-VM",
        ),
        pytest.param(
            {"os_dict": WINDOWS_LATEST},
            {
                "vm_name": "migrate-rhcos10-to-rhcos9-windows",
                "template_labels": WINDOWS_LATEST_LABELS,
                "vm_affinity": RHCOS10_AFFINITY,
            },
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm],
            id="WIN-VM",
        ),
    ],
    indirect=True,
)
def test_vm_migrates_from_rhcos10_to_rhcos9_node(
    admin_client: DynamicClient,
    dual_stream_migration_vm: VirtualMachineForTests,
) -> None:
    """
    Test that live migration from an RHCOS 10 worker node to an RHCOS 9 worker node
    completes successfully without restarting the VM.

    Preconditions:
        - Under-test VM running on an RHCOS 10 worker node

    Steps:
        1. Record VM boot time
        2. Live migrate the under-test VM to an RHCOS 9 worker node

    Expected:
        - Live migration completes successfully and the VM is running on an RHCOS 9 worker node
        - The VM did not restart during migration
    """
    boot_time = get_vm_boot_time(vm=dual_stream_migration_vm)
    set_vm_affinity(vm=dual_stream_migration_vm, affinity=RHCOS9_AFFINITY)
    migrate_vm_and_verify(vm=dual_stream_migration_vm, client=admin_client, check_ssh_connectivity=True)
    assert RHCOS9_WORKER_LABEL in dual_stream_migration_vm.vmi.get_node(privileged_client=admin_client).labels.keys(), (
        f"VM {dual_stream_migration_vm.name} is not running on an RHCOS 9 node after migration"
    )
    verify_guest_boot_time(
        vm_list=[dual_stream_migration_vm], initial_boot_time={dual_stream_migration_vm.name: boot_time}
    )


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_function, dual_stream_migration_vm",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {
                "vm_name": "migrate-rhcos9-to-rhcos10-rhel",
                "template_labels": RHEL_LATEST_LABELS,
                "vm_affinity": RHCOS9_AFFINITY,
            },
            marks=pytest.mark.polarion("CNV-16275"),
            id="RHEL-VM",
        ),
        pytest.param(
            {"os_dict": WINDOWS_LATEST},
            {
                "vm_name": "migrate-rhcos9-to-rhcos10-windows",
                "template_labels": WINDOWS_LATEST_LABELS,
                "vm_affinity": RHCOS9_AFFINITY,
            },
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm],
            id="WIN-VM",
        ),
    ],
    indirect=True,
)
def test_vm_migrates_from_rhcos9_to_rhcos10_node(
    admin_client: DynamicClient,
    dual_stream_migration_vm: VirtualMachineForTests,
) -> None:
    """
    Test that live migration from an RHCOS 9 worker node to an RHCOS 10 worker node
    completes successfully without restarting the VM.

    Preconditions:
        - Under-test VM running on an RHCOS 9 worker node

    Steps:
        1. Record VM boot time
        2. Live migrate the under-test VM to an RHCOS 10 worker node

    Expected:
        - Live migration completes successfully and the VM is running on an RHCOS 10 worker node
        - The VM did not restart during migration
    """
    boot_time = get_vm_boot_time(vm=dual_stream_migration_vm)
    set_vm_affinity(vm=dual_stream_migration_vm, affinity=RHCOS10_AFFINITY)
    migrate_vm_and_verify(vm=dual_stream_migration_vm, client=admin_client, check_ssh_connectivity=True)
    assert (
        RHCOS9_WORKER_LABEL not in dual_stream_migration_vm.vmi.get_node(privileged_client=admin_client).labels.keys()
    ), f"VM {dual_stream_migration_vm.name} is not running on an RHCOS 10 node after migration"
    verify_guest_boot_time(
        vm_list=[dual_stream_migration_vm], initial_boot_time={dual_stream_migration_vm.name: boot_time}
    )
