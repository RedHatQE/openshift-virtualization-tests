from __future__ import annotations

import ipaddress
from collections.abc import Generator
from typing import TYPE_CHECKING, Final

import pytest

from libs.net.ip import random_cidr_addresses_by_family
from libs.vm.oper import run_vm
from tests.network.sriov.libsriov import base_sriov_vm, vm_sriov_mac

if TYPE_CHECKING:
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
    namespace: Namespace,
    sriov_network: SriovNetwork,
) -> Generator[BaseVirtualMachine]:
    sriov_iface_addresses = random_cidr_addresses_by_family(net_seed=_NET_SEED, host_address=_HOTPLUG_VM_HOST_ADDRESS)
    with base_sriov_vm(
        namespace=namespace.name,
        name="sriov-memory-hotplug-vm",
        sriov_network_name=sriov_network.name,
        sriov_mac=vm_sriov_mac(mac_suffix_index=next(index_number)),
        addresses=sriov_iface_addresses,
        memory_guest=_INITIAL_MEMORY,
        memory_max_guest=_MAX_GUEST_MEMORY,
    ) as vm:
        addresses = vm.cloud_init_network_data.ethernets[_SRIOV_CLOUD_INIT_PROFILE].addresses or []
        run_vm(
            vm=vm,
            ip_addresses_by_spec_net_name={
                sriov_network.name: [str(ipaddress.ip_interface(addr).ip) for addr in addresses]
            },
        )
        yield vm


@pytest.fixture(scope="class")
def sriov_ref_vm(
    index_number: Generator[int],
    namespace: Namespace,
    sriov_network: SriovNetwork,
) -> Generator[BaseVirtualMachine]:
    sriov_iface_addresses = random_cidr_addresses_by_family(net_seed=_NET_SEED, host_address=_REF_VM_HOST_ADDRESS)
    with base_sriov_vm(
        namespace=namespace.name,
        name="sriov-ref-vm",
        sriov_network_name=sriov_network.name,
        sriov_mac=vm_sriov_mac(mac_suffix_index=next(index_number)),
        addresses=sriov_iface_addresses,
        memory_guest=_INITIAL_MEMORY,
    ) as vm:
        addresses = vm.cloud_init_network_data.ethernets[_SRIOV_CLOUD_INIT_PROFILE].addresses or []
        run_vm(
            vm=vm,
            ip_addresses_by_spec_net_name={
                sriov_network.name: [str(ipaddress.ip_interface(addr).ip) for addr in addresses]
            },
        )
        yield vm
