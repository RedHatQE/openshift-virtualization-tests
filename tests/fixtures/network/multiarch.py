from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.vm import BaseVirtualMachine
from utilities.constants.architecture import AMD_64, ARM_64

# ---------------------------------------------------------------------------
# Adaptive cross-arch pair fixture — pod network
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def arch_pair_vms(
    request: pytest.FixtureRequest,
    namespace: Namespace,
    unprivileged_client: DynamicClient,
) -> Generator[tuple[BaseVirtualMachine, BaseVirtualMachine]]:
    """Yield a started (vm_a, vm_b) pair where each VM runs on a different arch.

    Parametrized indirectly via pytest_generate_tests with
    ``request.param = (arch_a, arch_b)``.
    """
    arch_a, arch_b = request.param
    spec_a = base_vmspec()
    spec_a.template.spec.architecture = arch_a
    spec_b = base_vmspec()
    spec_b.template.spec.architecture = arch_b
    with (
        fedora_vm(
            namespace=namespace.name,
            name=f"{arch_a}-vm",
            client=unprivileged_client,
            spec=spec_a,
        ) as vm_a,
        fedora_vm(
            namespace=namespace.name,
            name=f"{arch_b}-vm",
            client=unprivileged_client,
            spec=spec_b,
        ) as vm_b,
    ):
        vm_a.start(wait=True)
        vm_a.wait_for_agent_connected()
        vm_b.start(wait=True)
        vm_b.wait_for_agent_connected()
        yield vm_a, vm_b


# ---------------------------------------------------------------------------
# Legacy single-arch fixtures — kept for backward compatibility
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def arm_vm(namespace: Namespace, unprivileged_client: DynamicClient) -> Generator[BaseVirtualMachine]:
    spec = base_vmspec()
    spec.template.spec.architecture = ARM_64
    with fedora_vm(namespace=namespace.name, name="arm-vm", client=unprivileged_client, spec=spec) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def amd_vm(namespace: Namespace, unprivileged_client: DynamicClient) -> Generator[BaseVirtualMachine]:
    spec = base_vmspec()
    spec.template.spec.architecture = AMD_64
    with fedora_vm(namespace=namespace.name, name="amd-vm", client=unprivileged_client, spec=spec) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm
