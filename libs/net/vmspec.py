import ipaddress
from collections.abc import Callable
from typing import Any, Final

from kubernetes.dynamic.client import ResourceField
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutExpiredError, TimeoutSampler, retry

from libs.vm.spec import Devices, Network, SpecDisk, VMISpec, Volume
from libs.vm.vm import BaseVirtualMachine

LOOKUP_IFACE_STATUS_TIMEOUT_SEC: Final[int] = 30
WAIT_FOR_MISSING_IFACE_STATUS_TIMEOUT_SEC: Final[int] = 120
RETRY_INTERVAL_SEC: Final[int] = 5
IP_ADDRESS: Final[str] = "ipAddress"


class VMInterfaceSpecNotFoundError(Exception):
    pass


class VMInterfaceStatusNotFoundError(Exception):
    pass


class VMInterfaceStatusStillExistsError(Exception):
    pass


class IpNotFound(Exception):
    pass


def _default_interface_predicate(interface: ResourceField) -> bool:
    return "guest-agent" in interface["infoSource"] and interface[IP_ADDRESS]


def lookup_iface_status(
    vm: VirtualMachine,
    iface_name: str,
    predicate: Callable[[Any], bool] = _default_interface_predicate,
    timeout: int = LOOKUP_IFACE_STATUS_TIMEOUT_SEC,
) -> ResourceField:
    """
    Awaits and returns the network interface status requested if found and the predicate function,
    otherwise raises VMInterfaceStatusNotFoundError.

    Args:
        vm: VM in which to search for the network interface.
        iface_name: The name of the requested interface.
        predicate: A function that takes a network interface as an argument
            and returns a boolean value. This function should define the condition that
            the interface needs to meet.
        timeout: Lookup operation timeout

    Returns:
        iface (ResourceField): The requested interface.

    Raises:
        VMInterfaceStatusNotFoundError: If the requested interface was not found in the vmi status.
    """
    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=RETRY_INTERVAL_SEC,
        func=_lookup_iface_status,
        vm=vm,
        iface_name=iface_name,
        predicate=predicate,
    )
    try:
        for iface in sampler:
            if iface:
                return iface
    except TimeoutExpiredError:
        raise VMInterfaceStatusNotFoundError(f"Network interface named {iface_name} was not found in VM {vm.name}.")


def _lookup_iface_status(vm: VirtualMachine, iface_name: str, predicate: Callable[[Any], bool]) -> ResourceField | None:
    """
    Returns the interface requested if found and the predicate function (to which the interface is
    sent) Else, returns None.

    Args:
        vm: VM in which to search for the network interface.
        iface_name: The name of the requested interface.
        predicate: A function that takes a network interface as an argument
            and returns a boolean value. this function should define the condition that
            the interface needs to meet.

    Returns:
        iface (ResourceField) | None: The requested interface or None
    """
    for iface in vm.vmi.interfaces:
        if iface.name == iface_name and predicate(iface):
            return iface
    return None


@retry(
    wait_timeout=WAIT_FOR_MISSING_IFACE_STATUS_TIMEOUT_SEC,
    sleep=RETRY_INTERVAL_SEC,
    exceptions_dict={VMInterfaceStatusStillExistsError: []},
)
def wait_for_missing_iface_status(vm: BaseVirtualMachine, iface_name: str) -> bool:
    """
    Waits for a network interface to be deleted from the virtual machine's interface status.

    Args:
        vm (BaseVirtualMachine): The virtual machine to check for the interface status.
        iface_name: (str): The name of the network interface to wait for deletion.

    Returns:
        bool: True if the interface is missing otherwise raises an exception.

    Raises:
        VMInterfaceStatusStillExistsError: If the interface still exists after the timeout period.
    """
    if _lookup_iface_status(vm=vm, iface_name=iface_name, predicate=lambda _: True) is not None:
        raise VMInterfaceStatusStillExistsError(f"Interface {iface_name} still exists in {vm.name}")

    return True


def lookup_primary_network(vm: BaseVirtualMachine) -> Network:
    for network in vm.instance.spec.template.spec.networks:
        if network.pod is not None:
            return Network(**network)
    raise VMInterfaceSpecNotFoundError(f"No interface connected to the primary network was found in VM {vm.name}.")


def add_volume_disk(vmi_spec: VMISpec, volume: Volume, disk: SpecDisk) -> VMISpec:
    vmi_spec.volumes = vmi_spec.volumes or []
    vmi_spec.volumes.append(volume)
    vmi_spec.domain.devices = vmi_spec.domain.devices or Devices()
    vmi_spec.domain.devices.disks = vmi_spec.domain.devices.disks or []
    vmi_spec.domain.devices.disks.append(disk)
    return vmi_spec


def lookup_iface_status_ip(
    vm: VirtualMachine, iface_name: str, ip_family: int
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """
    Return the IP address of the specified family for a VM interface.

    Args:
        vm: The virtual machine to query.
        iface_name: The name of the network interface.
        ip_family: The IP version (4 for IPv4, 6 for IPv6).

    Returns:
        The IP address matching the specified family.

    Raises:
        IpNotFound: If no IP address of the specified family is found.
    """
    try:
        iface = lookup_iface_status(
            vm=vm,
            iface_name=iface_name,
            predicate=lambda iface_status: bool(
                _lookup_first_ip_address(ip_addresses=iface_status.get("ipAddresses", []), ip_family=ip_family)
            ),
            timeout=120,
        )
    except VMInterfaceStatusNotFoundError:
        raise IpNotFound(f"IPv{ip_family} address not found for interface {iface_name} on VM {vm.name}.")

    return _lookup_first_ip_address(ip_addresses=iface["ipAddresses"], ip_family=ip_family)


def _lookup_first_ip_address(
    ip_addresses: list[str],
    ip_family: int,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    return next((ip for ip_addr in ip_addresses if (ip := ipaddress.ip_address(ip_addr)).version == ip_family), None)
