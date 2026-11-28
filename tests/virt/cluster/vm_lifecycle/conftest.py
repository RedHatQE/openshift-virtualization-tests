from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from utilities.constants import Images
from utilities.virt import VirtualMachineForTests, fedora_vm_body

if TYPE_CHECKING:
    from collections.abc import Iterator

    from kubernetes.dynamic import DynamicClient
    from ocp_resources.namespace import Namespace


@pytest.fixture(scope="class")
def run_strategy_container_vm(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    run_strategy: str,
) -> Iterator[VirtualMachineForTests]:
    """Class-scoped fedora container-disk VM created with the parametrized runStrategy."""
    name = "fedora-vm-run-strategy"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        run_strategy=run_strategy,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def run_strategy_dv_vm(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    run_strategy: str,
    golden_image_data_volume_template_for_test_scope_module: dict,
    cpu_for_migration: str | None,
) -> Iterator[VirtualMachineForTests]:
    """Class-scoped RHEL DV VM created with the parametrized runStrategy."""
    with VirtualMachineForTests(
        name="rhel-vm-run-strategy",
        namespace=namespace.name,
        client=unprivileged_client,
        memory_requests=Images.Rhel.DEFAULT_MEMORY_SIZE,
        run_strategy=run_strategy,
        data_volume_template=golden_image_data_volume_template_for_test_scope_module,
        cpu_model=cpu_for_migration,
    ) as vm:
        yield vm
