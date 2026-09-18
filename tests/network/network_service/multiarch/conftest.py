from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.service import Service

from libs.net.traffic_generator import IPERF_SERVER_PORT
from libs.vm.vm import BaseVirtualMachine
from tests.fixtures.network.multiarch import get_worker_arch_pairs


def pytest_generate_tests(metafunc):
    if "arch_pair_vms" in metafunc.fixturenames:
        pairs = get_worker_arch_pairs()
        metafunc.parametrize(
            "arch_pair_vms",
            pairs,
            indirect=True,
            ids=[f"{a}-{b}" for a, b in pairs],
            scope="class",
        )


@pytest.fixture()
def clusterip_service_for_vm_a(
    namespace: Namespace,
    unprivileged_client: DynamicClient,
    arch_pair_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> Generator[Service]:
    """ClusterIP Service exposing the first VM of the arch pair."""
    vm_a, _ = arch_pair_vms
    with Service(
        name=f"clusterip-svc-{vm_a.name}",
        namespace=namespace.name,
        selector={"vm.kubevirt.io/name": vm_a.name},
        ports=[{"port": IPERF_SERVER_PORT}],
        client=unprivileged_client,
    ) as svc:
        yield svc


@pytest.fixture()
def clusterip_service_for_vm_b(
    namespace: Namespace,
    unprivileged_client: DynamicClient,
    arch_pair_vms: tuple[BaseVirtualMachine, BaseVirtualMachine],
) -> Generator[Service]:
    """ClusterIP Service exposing the second VM of the arch pair."""
    _, vm_b = arch_pair_vms
    with Service(
        name=f"clusterip-svc-{vm_b.name}",
        namespace=namespace.name,
        selector={"vm.kubevirt.io/name": vm_b.name},
        ports=[{"port": IPERF_SERVER_PORT}],
        client=unprivileged_client,
    ) as svc:
        yield svc


# ---------------------------------------------------------------------------
# Legacy single-arch service fixtures — kept for backward compatibility
# ---------------------------------------------------------------------------


@pytest.fixture()
def clusterip_service_for_arm_vm(
    namespace: Namespace, unprivileged_client: DynamicClient, arm_vm: BaseVirtualMachine
) -> Generator[Service]:
    with Service(
        name="clusterip-svc-arm",
        namespace=namespace.name,
        selector={"vm.kubevirt.io/name": arm_vm.name},
        ports=[{"port": IPERF_SERVER_PORT}],
        client=unprivileged_client,
    ) as svc:
        yield svc


@pytest.fixture()
def clusterip_service_for_amd_vm(
    namespace: Namespace, unprivileged_client: DynamicClient, amd_vm: BaseVirtualMachine
) -> Generator[Service]:
    with Service(
        name="clusterip-svc-amd",
        namespace=namespace.name,
        selector={"vm.kubevirt.io/name": amd_vm.name},
        ports=[{"port": IPERF_SERVER_PORT}],
        client=unprivileged_client,
    ) as svc:
        yield svc
