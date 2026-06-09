from copy import deepcopy

from libs.net.vmspec import wait_for_no_vmi_condition, wait_for_vmi_condition_status
from libs.vm.vm import BaseVirtualMachine


def update_nad_references(vm: BaseVirtualMachine, nad_name_by_net: dict[str, str]) -> None:
    """Update secondary network NAD references and wait for the change to be fully applied.

    Patches the VM spec atomically, then waits for the MigrationRequired condition to
    appear (change detected) and disappear (migration completed).

    Args:
        vm: The virtual machine to update.
        nad_name_by_net: Mapping of spec network name to new NAD name.
    """
    resource_version = vm.vmi.instance.metadata.resourceVersion
    networks = deepcopy(vm.template_spec.networks) or []
    for network in networks:
        if network.name in nad_name_by_net and network.multus:
            network.multus.networkName = nad_name_by_net[network.name]
    vm.set_networks(networks=networks)
    wait_for_vmi_condition_status(vm=vm, condition="MigrationRequired", resource_version=resource_version)
    wait_for_no_vmi_condition(vm=vm, condition="MigrationRequired")
