from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.service import Service

from libs.net.traffic_generator import IPERF_SERVER_PORT
from libs.vm.vm import BaseVirtualMachine


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
