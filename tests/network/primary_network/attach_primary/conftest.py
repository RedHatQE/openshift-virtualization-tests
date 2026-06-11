"""Fixtures for VM network attachment tests."""

from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Devices
from libs.vm.vm import BaseVirtualMachine


@pytest.fixture()
def vm_without_pod_interface(namespace: Namespace, unprivileged_client: DynamicClient) -> Generator[BaseVirtualMachine]:
    """
    Create and start a VM with `autoattachPodInterface: false` and no interfaces/networks.

    Yields:
        BaseVirtualMachine: Running VM with autoattachPodInterface disabled
    """
    spec = base_vmspec()

    # Set no interfaces/networks and autoattachPodInterface to false
    spec.template.spec.domain.devices = Devices(autoattachPodInterface=False)
    spec.template.spec.networks = []

    with fedora_vm(
        namespace=namespace.name,
        name="vm-no-pod-interface",
        client=unprivileged_client,
        spec=spec,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm
