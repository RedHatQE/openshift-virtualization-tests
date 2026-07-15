from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.net.vmspec import lookup_iface_status
from libs.vm.affinity import new_node_affinity
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.connectivity import build_ping_command
from tests.network.primary_network.rhel9_rhel10_cluster.lib_helpers import primary_network_vm
from utilities.constants.cluster import RHCOS9_WORKER_LABEL


@pytest.fixture()
def primary_network_connectivity(
    primary_client_vm: BaseVirtualMachine,
    primary_server_vm: BaseVirtualMachine,
) -> None:
    primary_iface_name = primary_server_vm.vmi.interfaces[0].name
    for ip in lookup_iface_status(vm=primary_server_vm, iface_name=primary_iface_name)["ipAddresses"]:
        primary_client_vm.console(
            commands=[build_ping_command(dst_ip=ip, count=10, timeout=10)],
            timeout=20,
        )


@pytest.fixture(scope="class")
def primary_server_vm(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
) -> Generator[BaseVirtualMachine]:
    with primary_network_vm(
        namespace=namespace.name,
        name="server-vm",
        client=unprivileged_client,
        affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=True),
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def primary_client_vm(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
) -> Generator[BaseVirtualMachine]:
    with primary_network_vm(
        namespace=namespace.name,
        name="client-vm",
        client=unprivileged_client,
        affinity=new_node_affinity(key=RHCOS9_WORKER_LABEL, exists=True),
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm
