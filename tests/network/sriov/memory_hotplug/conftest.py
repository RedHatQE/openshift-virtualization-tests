import ipaddress
from collections.abc import Generator
from typing import TYPE_CHECKING, Final

import pytest

from libs.net.ip import random_cidr_addresses_by_family
from libs.net.vmspec import wait_for_ifaces_status
from libs.vm.oper import run_vms
from tests.network.sriov.libsriov import base_sriov_vm, vm_sriov_mac

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.namespace import Namespace
    from ocp_resources.sriov_network import SriovNetwork

    from libs.vm.vm import BaseVirtualMachine

_NET_SEED: Final[int] = 0
_HOTPLUG_VM_HOST_ADDRESS: Final[int] = 10
_REF_VM_HOST_ADDRESS: Final[int] = 11
_INITIAL_MEMORY: Final[str] = "1Gi"
_MAX_GUEST_MEMORY: Final[str] = "4Gi"
_SRIOV_CLOUD_INIT_PROFILE: Final[str] = "sriov"


@pytest.fixture(scope="class")
def sriov_vm_with_max_guest(
    index_number: Generator[int],
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    sriov_network: SriovNetwork,
) -> Generator[BaseVirtualMachine]:
    sriov_iface_addresses = random_cidr_addresses_by_family(net_seed=_NET_SEED, host_address=_HOTPLUG_VM_HOST_ADDRESS)
    with base_sriov_vm(
        namespace=namespace.name,
        name="sriov-memory-hotplug-vm",
        client=unprivileged_client,
        sriov_network_name=sriov_network.name,
        sriov_mac=vm_sriov_mac(mac_suffix_index=next(index_number)),
        addresses=sriov_iface_addresses,
        memory_guest=_INITIAL_MEMORY,
        memory_max_guest=_MAX_GUEST_MEMORY,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def sriov_ref_vm(
    index_number: Generator[int],
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    sriov_network: SriovNetwork,
) -> Generator[BaseVirtualMachine]:
    sriov_iface_addresses = random_cidr_addresses_by_family(net_seed=_NET_SEED, host_address=_REF_VM_HOST_ADDRESS)
    with base_sriov_vm(
        namespace=namespace.name,
        name="sriov-ref-vm",
        client=unprivileged_client,
        sriov_network_name=sriov_network.name,
        sriov_mac=vm_sriov_mac(mac_suffix_index=next(index_number)),
        addresses=sriov_iface_addresses,
        memory_guest=_INITIAL_MEMORY,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def running_sriov_vms(
    sriov_ref_vm: BaseVirtualMachine,
    sriov_vm_with_max_guest: BaseVirtualMachine,
    sriov_network: SriovNetwork,
) -> tuple[BaseVirtualMachine, BaseVirtualMachine]:
    run_vms(vms=(sriov_ref_vm, sriov_vm_with_max_guest))
    for vm in (sriov_ref_vm, sriov_vm_with_max_guest):
        addresses = vm.cloud_init_network_data.ethernets[_SRIOV_CLOUD_INIT_PROFILE].addresses or []
        wait_for_ifaces_status(
            vm=vm,
            ip_addresses_by_spec_net_name={
                sriov_network.name: [str(ipaddress.ip_interface(addr).ip) for addr in addresses]
            },
        )
    return sriov_ref_vm, sriov_vm_with_max_guest
