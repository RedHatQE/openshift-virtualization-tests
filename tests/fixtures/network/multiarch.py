from collections.abc import Generator
from functools import cache
from itertools import combinations

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork

from libs.net.udn import UDN_BINDING_DEFAULT_PLUGIN_NAME
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.oper import run_vms
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.vm_factory import udn_vm
from utilities.cluster import cache_admin_client
from utilities.constants.architecture import AMD_64, ARM_64
from utilities.constants.cluster import KUBERNETES_ARCH_LABEL, WORKER_NODE_LABEL_KEY

# ---------------------------------------------------------------------------
# Architecture discovery helpers
# ---------------------------------------------------------------------------


@cache
def get_worker_archs() -> frozenset[str]:
    """Return all distinct architectures present on worker nodes.

    Result is cached for the process lifetime so Node.get() is called only
    once per test session.
    """
    return frozenset(
        node.labels[KUBERNETES_ARCH_LABEL]
        for node in Node.get(client=cache_admin_client())
        if node.labels.get(WORKER_NODE_LABEL_KEY) is not None and node.labels.get(KUBERNETES_ARCH_LABEL)
    )


def get_worker_arch_pairs() -> list[tuple[str, str]]:
    """Return all unique sorted pairs of worker architectures.

    Examples:
        2-arch cluster (arm64 + s390x)        -> [("arm64", "s390x")]
        3-arch cluster (amd64 + arm64 + s390x) -> [("amd64", "arm64"),
                                                    ("amd64", "s390x"),
                                                    ("arm64", "s390x")]
    """
    return sorted(combinations(sorted(get_worker_archs()), 2))


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
# Adaptive cross-arch pair fixture — User Defined Network
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def arch_pair_udn_vms(
    request: pytest.FixtureRequest,
    admin_client: DynamicClient,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
) -> Generator[tuple[BaseVirtualMachine, BaseVirtualMachine]]:
    """Yield a started (vm_a, vm_b) UDN pair for the given (arch_a, arch_b) param.

    Both VMs are connected to the primary UDN and started in parallel via
    ``run_vms()``.  Parametrized indirectly via pytest_generate_tests.
    """
    arch_a, arch_b = request.param
    with (
        udn_vm(
            namespace_name=namespaced_layer2_user_defined_network.namespace,
            name=f"{arch_a}-udn-vm",
            client=admin_client,
            binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
            architecture=arch_a,
        ) as vm_a,
        udn_vm(
            namespace_name=namespaced_layer2_user_defined_network.namespace,
            name=f"{arch_b}-udn-vm",
            client=admin_client,
            binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
            architecture=arch_b,
        ) as vm_b,
    ):
        run_vms(vms=(vm_a, vm_b))
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
