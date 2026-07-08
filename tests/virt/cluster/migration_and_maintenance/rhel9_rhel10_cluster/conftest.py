from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

import pytest

from utilities.constants.virt import REGEDIT_PROC_NAME
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    start_and_fetch_processid_on_linux_vm,
    start_and_fetch_processid_on_windows_vm,
    vm_instance_from_template,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.namespace import Namespace


@pytest.fixture
def dual_stream_migration_vm(
    request: pytest.FixtureRequest,
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    golden_image_data_volume_template_for_test_scope_function: dict[str, Any],
    modern_cpu_for_migration: str | None,
) -> Generator[VirtualMachineForTestsFromTemplate]:
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_test_scope_function,
        vm_cpu_model=modern_cpu_for_migration,
        vm_affinity=request.param.get("vm_affinity"),
    ) as vm:
        yield vm


@pytest.fixture
def vm_background_process_id(dual_stream_migration_vm: VirtualMachineForTests) -> int:
    if "windows" in dual_stream_migration_vm.name:
        return start_and_fetch_processid_on_windows_vm(vm=dual_stream_migration_vm, process_name=REGEDIT_PROC_NAME)
    return start_and_fetch_processid_on_linux_vm(vm=dual_stream_migration_vm, process_name="ping", args="localhost")
