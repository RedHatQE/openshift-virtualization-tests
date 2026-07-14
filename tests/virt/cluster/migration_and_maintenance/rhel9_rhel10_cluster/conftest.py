from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

import pytest

from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    vm_instance_from_template,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.namespace import Namespace


@pytest.fixture()
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
