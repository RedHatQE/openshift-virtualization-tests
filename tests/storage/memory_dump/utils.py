from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import retry

from utilities.constants import TIMEOUT_2MIN, TIMEOUT_3MIN, TIMEOUT_5SEC


class MemoryDumpPhaseCompletedError(Exception):
    pass


class MemoryDumpPhaseRemovedError(Exception):
    pass


@retry(
    wait_timeout=TIMEOUT_3MIN,
    sleep=TIMEOUT_5SEC,
    exceptions_dict={MemoryDumpPhaseCompletedError: []},
)
def wait_for_memory_dump_status_completed(vm: VirtualMachine) -> bool:
    vm_memory_dump_phase = vm.instance.status.get("memoryDumpRequest", {}).get("phase")
    if vm_memory_dump_phase == VirtualMachine.Status.COMPLETED:
        return True
    raise MemoryDumpPhaseCompletedError(f"VM {vm.name} memoryDumpRequest.phase is {vm_memory_dump_phase}")


@retry(
    wait_timeout=TIMEOUT_2MIN,
    sleep=TIMEOUT_5SEC,
    exceptions_dict={MemoryDumpPhaseRemovedError: []},
)
def wait_for_memory_dump_status_removed(vm: VirtualMachine) -> bool:
    vm_memory_dump_request = vm.instance.status.memoryDumpRequest
    if vm_memory_dump_request is None:
        return True
    raise MemoryDumpPhaseRemovedError(f"VM {vm.name} status.memoryDumpRequest is {vm_memory_dump_request}")
