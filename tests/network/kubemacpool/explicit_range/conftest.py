from collections.abc import Generator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.namespace import Namespace
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.virtual_machine import VirtualMachine

from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Interface, Multus, Network
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.mac import random_mac_range
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.network import MacPool


@pytest.fixture()
def custom_mac_range_vm(
    kubemacpool_random_range_config_hco: None,
    unprivileged_client: DynamicClient,
    namespace: Namespace,
) -> Generator[BaseVirtualMachine]:

    spec = base_vmspec()

    spec.runStrategy = VirtualMachine.RunStrategy.HALTED

    secondary_iface_name = "custom-mac-range-hco"
    spec.template.spec.networks = [
        Network(name=secondary_iface_name, multus=Multus(networkName=secondary_iface_name)),
    ]

    spec.template.spec.domain.devices.interfaces = [  # type: ignore
        Interface(name=secondary_iface_name, bridge={}),
    ]

    with fedora_vm(
        namespace=namespace.name,
        name="vm-custom-mac-range",
        client=unprivileged_client,
        spec=spec,
    ) as vm:
        vm.wait(timeout=30)  # Wait for VM creation to complete, failed KMP MAC assignment would fail VM creation
        yield vm


@pytest.fixture()
def kubemacpool_random_range_config_hco(
    admin_client: DynamicClient,
    hyperconverged_resource_scope_function: HyperConverged,
) -> Generator[None]:
    rand_range_start, rand_range_end = random_mac_range(range_seed=0)

    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {
                    "kubeMacPoolConfiguration": {
                        "rangeStart": rand_range_start,
                        "rangeEnd": rand_range_end,
                    }
                }
            }
        },
        list_resource_reconcile=[NetworkAddonsConfig],
        wait_for_reconcile_post_update=True,
        admin_client=admin_client,
    ):
        yield


@pytest.fixture()
def custom_range_hco_mac_pool(
    kubemacpool_random_range_config_hco: None,
    hyperconverged_resource_scope_function: HyperConverged,
) -> MacPool:
    hco_instance = hyperconverged_resource_scope_function.instance
    kmp_range_from_hco = {
        "RANGE_START": hco_instance.spec.kubeMacPoolConfiguration.rangeStart,
        "RANGE_END": hco_instance.spec.kubeMacPoolConfiguration.rangeEnd,
    }

    return MacPool(kmp_range=kmp_range_from_hco)
