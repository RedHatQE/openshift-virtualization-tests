from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from utilities.constants.architecture import AMD_64, ARM_64

from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.vm import BaseVirtualMachine


@pytest.fixture(scope="class")
def arm_vm(namespace: Namespace, unprivileged_client: DynamicClient) -> Generator[BaseVirtualMachine]:
    spec = base_vmspec()
    spec.template.spec.architecture = ARM_64
    vm = fedora_vm(namespace=namespace.name, name="arm-vm", client=unprivileged_client, spec=spec)
    with vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def amd_vm(namespace: Namespace, unprivileged_client: DynamicClient) -> Generator[BaseVirtualMachine]:
    spec = base_vmspec()
    spec.template.spec.architecture = AMD_64
    vm = fedora_vm(namespace=namespace.name, name="amd-vm", client=unprivileged_client, spec=spec)
    with vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm
