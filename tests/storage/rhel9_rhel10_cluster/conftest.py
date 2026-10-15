from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest

from tests.storage.constants import BLANK_DV_SIZE, TEST_FILE_CONTENT
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
    from ocp_resources.datavolume import DataVolume
    from ocp_resources.namespace import Namespace


@contextmanager
def _written_test_data(
    namespace: Namespace,
    vm: VirtualMachineForTests,
    dv: DataVolume,
) -> Generator[str]:
    with virtctl_volume(
        action="add",
        namespace=namespace.name,
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
def vm_with_hotplug_on_rhcos9(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    fedora_data_source_scope_module,
    modern_cpu_for_migration: str | None,
) -> Generator[VirtualMachineForTests]:
    with VirtualMachineForTests(
        name="vm-hotplug-rhcos9",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
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
) -> Generator[VirtualMachineForTests]:
    with VirtualMachineForTests(
        name="vm-hotplug-rhcos10",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
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
) -> Generator[DataVolume]:
    with create_dv(
        client=unprivileged_client,
        source="blank",
        dv_name="blank-dv-hotplug-migration",
        namespace=namespace.name,
        size=BLANK_DV_SIZE,
        consume_wffc=False,
    ) as dv:
        yield dv


@pytest.fixture()
def written_test_data_on_rhcos9(
    namespace: Namespace,
    vm_with_hotplug_on_rhcos9: VirtualMachineForTests,
    blank_dv_for_hotplug: DataVolume,
) -> Generator[str]:
    with _written_test_data(namespace=namespace, vm=vm_with_hotplug_on_rhcos9, dv=blank_dv_for_hotplug) as data:
        yield data


@pytest.fixture()
def written_test_data_on_rhcos10(
    namespace: Namespace,
    vm_with_hotplug_on_rhcos10: VirtualMachineForTests,
    blank_dv_for_hotplug: DataVolume,
) -> Generator[str]:
    with _written_test_data(namespace=namespace, vm=vm_with_hotplug_on_rhcos10, dv=blank_dv_for_hotplug) as data:
        yield data
