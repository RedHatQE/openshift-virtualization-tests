from collections.abc import Callable
from typing import Any, Final

from kubernetes.dynamic.client import ResourceField
from timeout_sampler import TimeoutExpiredError, retry

from libs.vm.spec import Network
from libs.vm.vm import BaseVirtualMachine

LOOKUP_IFACE_STATUS_TIMEOUT_SEC: Final[int] = 30
RETRY_INTERVAL_SEC: Final[int] = 5


class VMInterfaceSpecNotFoundError(Exception):
    pass


class VMInterfaceStatusNotFoundError(Exception):
    pass


def lookup_iface_status(vm: BaseVirtualMachine, iface_name: str) -> ResourceField:
    """
    Returns the network interface status requested if found, otherwise raises VMInterfaceStatusNotFoundError.
    The interface status information is expected to be sourced from the guest-agent with an IP address.

    Args:
        vm (BaseVirtualMachine): VM in which to search for the network interface.
        iface_name (str): The name of the requested interface.

    Returns:
        iface (ResourceField): The requested interface.

    Raises:
        VMInterfaceStatusNotFoundError: If the requested interface was not found in the vmi status.
    """
    try:
        return _lookup_iface_status(
            vm=vm,
            iface_name=iface_name,
            predicate=lambda interface: "guest-agent" in interface["infoSource"] and interface["ipAddress"],
        )
    except TimeoutExpiredError:
        raise VMInterfaceStatusNotFoundError(f"Network interface named {iface_name} was not found in VM {vm.name}.")


@retry(
    wait_timeout=LOOKUP_IFACE_STATUS_TIMEOUT_SEC,
    sleep=RETRY_INTERVAL_SEC,
    exceptions_dict={VMInterfaceStatusNotFoundError: []},
)
def _lookup_iface_status(vm: BaseVirtualMachine, iface_name: str, predicate: Callable[[Any], bool]) -> ResourceField:
    """
    Returns the interface requested if found and the predicate function (to which the interface is
    sent) returns True. Else, raise VMInterfaceStatusNotFoundError.

    Args:
        vm (BaseVirtualMachine): VM in which to search for the network interface.
        iface_name (str): The name of the requested interface.
        predicate (Callable[[dict[str, Any]], bool]): A function that takes a network interface as an argument
            and returns a boolean value. this function should define the condition that
            the interface needs to meet.

    Returns:
        iface (ResourceField): The requested interface.

    Raises:
        VMInterfaceStatusNotFoundError: If the requested interface was not found in the VM.
    """
    for iface in vm.vmi.interfaces:
        if iface.name == iface_name and predicate(iface):
            return iface
    raise VMInterfaceStatusNotFoundError(f"Network interface named {iface_name} was not found in VM {vm.name}.")


def lookup_primary_network(vm: BaseVirtualMachine) -> Network:
    for network in vm.instance.spec.template.spec.networks:
        if network.pod is not None:
            return Network(**network)
    raise VMInterfaceSpecNotFoundError(f"No interface connected to the primary network was found in VM {vm.name}.")
