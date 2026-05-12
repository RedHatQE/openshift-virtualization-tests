from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.net.netattachdef import NetworkAttachmentDefinition
from libs.vm.vm import BaseVirtualMachine
from tests.network.l2_bridge.vmi_interfaces_stability.lib_helpers import (
    secondary_network_vm,
    wait_for_stable_ifaces,
)


@pytest.fixture(scope="class")
def running_linux_bridge_vm(
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    bridge_nad: NetworkAttachmentDefinition,
) -> Generator[BaseVirtualMachine]:
    with secondary_network_vm(
        namespace=namespace.name,
        name="vm-iface-stability",
        client=unprivileged_client,
        bridge_network_name=bridge_nad.name,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        wait_for_stable_ifaces(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def stable_ips(running_linux_bridge_vm: BaseVirtualMachine) -> dict[str, str]:
    return {iface.name: iface.ipAddress for iface in running_linux_bridge_vm.vmi.interfaces}
