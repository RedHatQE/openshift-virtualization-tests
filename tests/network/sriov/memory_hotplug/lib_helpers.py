from kubernetes.utils.quantity import parse_quantity
from timeout_sampler import retry

from libs.vm.vm import BaseVirtualMachine
from utilities.constants import TIMEOUT_5MIN, TIMEOUT_5SEC


def hotplug_memory_and_wait(vm: BaseVirtualMachine, memory_guest: str) -> None:
    """Hot-plug memory on a VM and wait for the guest OS to report the new amount.

    Sets the new guest memory value on the VM, then polls the VMI status
    guestCurrent field until it reaches the expected value — confirming the
    live migration triggered by the hot-plug has completed and the guest OS
    has received the memory.

    Args:
        vm: The virtual machine to hot-plug memory on.
        memory_guest: New guest memory value (e.g. "2Gi").
    """
    vm.set_guest_memory(memory_guest=memory_guest)
    _wait_for_guest_memory_in_vmi_status(vm=vm, memory_guest=memory_guest)


@retry(wait_timeout=TIMEOUT_5MIN, sleep=TIMEOUT_5SEC)
def _wait_for_guest_memory_in_vmi_status(vm: BaseVirtualMachine, memory_guest: str) -> bool:
    current = vm.vmi.instance.status.memory.guestCurrent
    return bool(current) and parse_quantity(str(current)) == parse_quantity(memory_guest)
