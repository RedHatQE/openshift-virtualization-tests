"""
Pytest conftest for dual-stream (RHCOS9/RHCOS10) tests
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest

from tests.storage.constants import BLANK_DV_SIZE, TEST_FILE_CONTENT
from tests.storage.rhel9_rhel10_cluster.constants import SNAPSHOT_TEST_DATA, SNAPSHOT_TEST_FILE
from tests.storage.rhel9_rhel10_cluster.utils import (
    HOTPLUG_DISK_SERIAL,
    HOTPLUG_TEST_FILE,
    prepare_hotplug_disk,
)
from utilities.constants.cluster import RHCOS9_AFFINITY, RHCOS10_AFFINITY
from utilities.storage import (
    create_dv,
    data_volume_template_with_source_ref_dict,
    virtctl_volume,
    wait_for_vm_volume_ready,
    write_file_via_ssh,
)
from utilities.virt import VirtualMachineForTests, running_vm

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.data_source import DataSource
    from ocp_resources.datavolume import DataVolume
    from ocp_resources.namespace import Namespace


@contextmanager
def _written_test_data(
    vm: VirtualMachineForTests,
    dv: DataVolume,
) -> Generator[str]:
    with virtctl_volume(
        action="add",
        namespace=vm.namespace,
        vm_name=vm.name,
        volume_name=dv.name,
        serial=HOTPLUG_DISK_SERIAL,
    ) as res:
        status, out, err = res
        assert status, f"Failed to hotplug volume: out={out}, err={err}"
        wait_for_vm_volume_ready(vm=vm, volume_name=dv.name)
        prepare_hotplug_disk(vm=vm, serial=HOTPLUG_DISK_SERIAL)
        write_file_via_ssh(vm=vm, filename=HOTPLUG_TEST_FILE, content=TEST_FILE_CONTENT)
        yield TEST_FILE_CONTENT


@pytest.fixture()
def dual_stream_snapshot_vm(
    request: pytest.FixtureRequest,
    unprivileged_client,
    namespace: Namespace,
    rhel10_data_source_scope_session: DataSource,
    storage_class_matrix_snapshot_matrix__function__: dict,
) -> Generator[VirtualMachineForTests]:
    """Create RHEL VM on a specified RHCOS node, write test data, and stop it.

    VM is created with affinity to source RHCOS version, brought up, test data
    written to disk, then stopped in preparation for snapshot/restore testing.

    Yields:
        VirtualMachineForTests: Stopped VM with test data on disk, ready for snapshot.
    """
    with VirtualMachineForTests(
        name=request.param["vm_name"],
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel10_data_source_scope_session,
            storage_class=next(iter(storage_class_matrix_snapshot_matrix__function__)),
        ),
        vm_affinity=request.param["vm_affinity"],
    ) as vm:
        running_vm(vm=vm)
        write_file_via_ssh(vm=vm, filename=SNAPSHOT_TEST_FILE, content=SNAPSHOT_TEST_DATA)
        vm.stop(wait=True)
        yield vm


@pytest.fixture()
def vm_with_hotplug_on_rhcos9(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    fedora_data_source_scope_module,
    modern_cpu_for_migration: str | None,
    rwx_storage_class_name_scope_module: str,
) -> Generator[VirtualMachineForTests]:
    with VirtualMachineForTests(
        name="vm-hotplug-rhcos9",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
            storage_class=rwx_storage_class_name_scope_module,
        ),
        cpu_model=modern_cpu_for_migration,
        vm_affinity=RHCOS9_AFFINITY,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_with_hotplug_on_rhcos10(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    fedora_data_source_scope_module,
    modern_cpu_for_migration: str | None,
    rwx_storage_class_name_scope_module: str,
) -> Generator[VirtualMachineForTests]:
    with VirtualMachineForTests(
        name="vm-hotplug-rhcos10",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
            storage_class=rwx_storage_class_name_scope_module,
        ),
        cpu_model=modern_cpu_for_migration,
        vm_affinity=RHCOS10_AFFINITY,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def blank_dv_for_hotplug(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    rwx_storage_class_name_scope_module: str,
    unique_suffix_scope_function: str,
) -> Generator[DataVolume]:
    with create_dv(
        client=unprivileged_client,
        source="blank",
        dv_name=f"blank-dv-hotplug-migration-{unique_suffix_scope_function}",
        namespace=namespace.name,
        size=BLANK_DV_SIZE,
        storage_class=rwx_storage_class_name_scope_module,
        consume_wffc=False,
    ) as dv:
        yield dv


@pytest.fixture()
def written_test_data_on_rhcos9(
    vm_with_hotplug_on_rhcos9: VirtualMachineForTests,
    blank_dv_for_hotplug: DataVolume,
) -> Generator[str]:
    with _written_test_data(vm=vm_with_hotplug_on_rhcos9, dv=blank_dv_for_hotplug) as data:
        yield data


@pytest.fixture()
def written_test_data_on_rhcos10(
    vm_with_hotplug_on_rhcos10: VirtualMachineForTests,
    blank_dv_for_hotplug: DataVolume,
) -> Generator[str]:
    with _written_test_data(vm=vm_with_hotplug_on_rhcos10, dv=blank_dv_for_hotplug) as data:
        yield data
