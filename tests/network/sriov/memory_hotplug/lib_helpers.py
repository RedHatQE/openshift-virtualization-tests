from kubernetes.utils.quantity import parse_quantity
from timeout_sampler import retry

from libs.vm.vm import BaseVirtualMachine
from utilities.constants import TIMEOUT_5MIN, TIMEOUT_5SEC
from utilities.infra import is_jira_open


def hotplug_memory_and_wait(vm: BaseVirtualMachine, memory_guest: str) -> None:
    """Hot-plug memory on a VM and wait for the guest OS to report the new amount.

    Sets the new guest memory value on the VM, then polls VMI status guestCurrent.
    While CNV-93556 is open (guestCurrent not updated after memory hotplug migration), falls
    back to reading /proc/meminfo via console as the authoritative memory check.

    Args:
        vm: The virtual machine to hot-plug memory on.
        memory_guest: New guest memory value (e.g. "2Gi").
    """
    vm.set_guest_memory(memory_guest=memory_guest)
    if is_jira_open(jira_id="CNV-93556"):
        _wait_for_guest_memory_in_proc_meminfo(vm=vm, memory_guest=memory_guest)
    else:
        _wait_for_guest_memory_in_vmi_status(vm=vm, memory_guest=memory_guest)


@retry(wait_timeout=TIMEOUT_5MIN, sleep=TIMEOUT_5SEC)
def _wait_for_guest_memory_in_vmi_status(vm: BaseVirtualMachine, memory_guest: str) -> bool:
    current = vm.vmi.instance.status.memory.guestCurrent
    return bool(current) and parse_quantity(str(current)) == parse_quantity(memory_guest)


@retry(wait_timeout=TIMEOUT_5MIN, sleep=30)
def _wait_for_guest_memory_in_proc_meminfo(vm: BaseVirtualMachine, memory_guest: str) -> bool:
    """Read MemTotal from /proc/meminfo via VM console.

    Args:
        vm: The virtual machine to check memory on.
        memory_guest: Expected guest memory value (e.g. "2Gi").
    """
    expected_kb = int(parse_quantity(memory_guest)) // 1024
    threshold = expected_kb * 95 // 100
    vm.console(
        commands=[f"awk '/MemTotal/{{exit ($2<{threshold})}}' /proc/meminfo"],
        timeout=30,
    )
    return True
