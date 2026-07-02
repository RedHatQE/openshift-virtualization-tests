from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork

from libs.net.ip import random_ipv4_address
from libs.net.udn import UDN_BINDING_DEFAULT_PLUGIN_NAME
from libs.vm import affinity
from libs.vm.oper import run_vms
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.vm_factory import udn_vm
from utilities.constants.architecture import AMD_64, ARM_64
from utilities.infra import create_ns


@pytest.fixture(scope="module")
def udn_namespace(admin_client):
    yield from create_ns(
        admin_client=admin_client,
        name="test-user-defined-network-ns",
        labels={"k8s.ovn.org/primary-user-defined-network": ""},
    )


@pytest.fixture(scope="module")
def namespaced_layer2_user_defined_network(admin_client, udn_namespace):
    with Layer2UserDefinedNetwork(
        name="layer2-udn",
        namespace=udn_namespace.name,
        role="Primary",
        subnets=[f"{random_ipv4_address(net_seed=0, host_address=0)}/24"],
        ipam={"lifecycle": "Persistent"},
        client=admin_client,
    ) as udn:
        udn.wait_for_condition(
            condition="NetworkAllocationSucceeded",
            status=udn.Condition.Status.TRUE,
        )
        yield udn


@pytest.fixture(scope="module")
def udn_affinity_label():
    return affinity.new_label(key_prefix="udn")


@pytest.fixture(scope="class")
def arm64_udn_vm(
    admin_client: DynamicClient,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
) -> Generator[BaseVirtualMachine]:
    """
    ARM64 VM with UDN as primary interface.
    """
    with udn_vm(
        namespace_name=namespaced_layer2_user_defined_network.namespace,
        name="arm64-udn-vm",
        client=admin_client,
        binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
        architecture=ARM_64,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def amd64_udn_vm(
    admin_client: DynamicClient,
    namespaced_layer2_user_defined_network: Layer2UserDefinedNetwork,
) -> Generator[BaseVirtualMachine]:
    """
    AMD64 VM with UDN as primary interface.
    """
    with udn_vm(
        namespace_name=namespaced_layer2_user_defined_network.namespace,
        name="amd64-udn-vm",
        client=admin_client,
        binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
        architecture=AMD_64,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def running_amd_and_arm_vms(
    amd64_udn_vm: BaseVirtualMachine, arm64_udn_vm: BaseVirtualMachine
) -> tuple[BaseVirtualMachine, BaseVirtualMachine]:
    """
    Start AMD64 and ARM64 UDN VMs in parallel.

    Returns:
        Tuple of (amd64_vm, arm64_vm) both running with agent connected.
    """
    amd64_vm, arm64_vm = run_vms(vms=(amd64_udn_vm, arm64_udn_vm))
    return amd64_vm, arm64_vm
