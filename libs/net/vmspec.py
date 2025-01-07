from timeout_sampler import TimeoutExpiredError, TimeoutSampler


class VMInterfaceNotFoundError(Exception):
    pass


def get_iface(vm, iface_name):
    try:
        return wait_for_vm_iface(
            vm=vm,
            iface_name=iface_name,
            timeout=30,
            sleep=5,
            predicate=lambda interface: "guest-agent" in interface["infoSource"] and interface["ipAddress"],
        )
    except TimeoutExpiredError:
        raise VMInterfaceNotFoundError(f"Network interface named {iface_name} was not found in VM {vm.name}.")


def wait_for_vm_iface(vm, iface_name, timeout, sleep, predicate=lambda iface: True):
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=sleep,
        func=iface_lookup,
        vm=vm,
        iface_name=iface_name,
        predicate=predicate,
        exceptions_dict={VMInterfaceNotFoundError: []},
    )
    for sample in samples:
        if sample:
            return sample


def iface_lookup(vm, iface_name, predicate):
    """
    Returns the interface requested if found and the predicate function (to which the interface is
    sent) returns True. Else, raise VMInterfaceNotFound.

    Args:
        vm (BaseVirtualMachine): VM in which to search for the network interface.
        iface_name (str): The name of the requested interface.
        predicate (function): A function that takes a network interface as an argument
            and returns a boolean value. This function should define the condition that
            the interface needs to meet.

    Returns:
        iface (dict): The requested interface.

    Raises:
        VMInterfaceNotFound: If the requested interface was not found in the VM.
    """
    for iface in vm.vmi.interfaces:
        if iface.name == iface_name and predicate(iface):
            return iface
    raise VMInterfaceNotFoundError(f"Network interface named {iface_name} was not found in VM {vm.name}.")
