"""Shared VM fixtures for multi-disk testing across storage features."""

import pytest

from tests.storage.snapshots.constants import NUM_BLANK_DISKS  # noqa: NIT001
from tests.storage.utils import VMWithSeveralBlankDisks  # noqa: NIT001
from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import running_vm


@pytest.fixture()
def vm_with_4_disks(
    skip_if_no_storage_class_for_snapshot,
    unprivileged_client,
    namespace,
    fedora_data_source_scope_module,
    snapshot_storage_class_name_scope_module,
):
    """Create a Fedora VM with 4 disks (1 boot + 3 blank) for multi-disk tests.

    Dynamically infers instance type and preference for the test cluster's architecture.
    Automatically skips if no VolumeSnapshot-capable StorageClass is available.

    Yields:
        VirtualMachineForTests: Running 4-disk Fedora VM with SSH connectivity.
    """
    with VMWithSeveralBlankDisks(
        name="fedora-4-disks",
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_FEDORA,
        blank_disk_storage_class_name=snapshot_storage_class_name_scope_module,
        num_blank_disks=NUM_BLANK_DISKS,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
            storage_class=snapshot_storage_class_name_scope_module,
        ),
        vm_instance_type_infer=True,
        vm_preference_infer=True,
    ) as vm:
        running_vm(vm=vm)
        yield vm
