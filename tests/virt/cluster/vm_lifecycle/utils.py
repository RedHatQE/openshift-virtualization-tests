from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from kubernetes.client.rest import ApiException
from ocp_resources.pod import Pod
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance import VirtualMachineInstance
from rrmngmnt import power_manager
from timeout_sampler import TimeoutSampler

from utilities.constants.timeouts import TIMEOUT_5SEC, TIMEOUT_10MIN
from utilities.virt import migrate_vm_and_verify, wait_for_running_vm

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)

MANUAL = VirtualMachine.RunStrategy.MANUAL
ALWAYS = VirtualMachine.RunStrategy.ALWAYS
HALTED = VirtualMachine.RunStrategy.HALTED
RERUNONFAILURE = VirtualMachine.RunStrategy.RERUNONFAILURE

RUN_STRATEGY_DICT = {
    MANUAL: {
        "start": {"status": True, "run_strategy": MANUAL},
        "restart": {"status": True, "run_strategy": MANUAL},
        "stop": {"status": None, "run_strategy": MANUAL},
    },
    ALWAYS: {
        "start": {
            "status": True,
            "run_strategy": ALWAYS,
            "expected_exceptions": [
                ".*Always does not support manual start requests.*",
                ".*VM is already running.*",
            ],
        },
        "restart": {"status": True, "run_strategy": ALWAYS},
        "stop": {"status": None, "run_strategy": HALTED},
    },
    HALTED: {
        "start": {"status": True, "run_strategy": ALWAYS},
        "restart": {"status": True, "run_strategy": ALWAYS},
        "stop": {"status": None, "run_strategy": HALTED},
    },
    RERUNONFAILURE: {
        "start": {
            "status": True,
            "run_strategy": RERUNONFAILURE,
            "expected_exceptions": [
                ".*RerunOnFailure does not support starting VM from failed state.*",
                ".*VM is already running.*",
            ],
        },
        "restart": {
            "status": True,
            "run_strategy": RERUNONFAILURE,
        },
        "stop": {
            "status": None,
            "run_strategy": RERUNONFAILURE,
        },
    },
}

# Expected VMI and virt-launcher pod statuses after guest OS shutdown.
RUN_STRATEGY_SHUTDOWN_STATUS = {
    MANUAL: {
        "vmi": VirtualMachineInstance.Status.SUCCEEDED,
        "launcher_pod": Pod.Status.SUCCEEDED,
    },
    RERUNONFAILURE: {
        "vmi": None,
        "launcher_pod": None,
    },
    ALWAYS: {
        "vmi": VirtualMachineInstance.Status.RUNNING,
        "launcher_pod": Pod.Status.RUNNING,
    },
}

# Transient printableStatus values where start/stop/restart may race.
_TRANSIENT_VM_STATUSES = frozenset({
    VirtualMachine.Status.STARTING,
    VirtualMachine.Status.STOPPING,
    VirtualMachine.Status.TERMINATING,
    VirtualMachine.Status.MIGRATING,
    VirtualMachine.Status.WAITING_FOR_VOLUME_BINDING,
    VirtualMachine.Status.PROVISIONING,
})


def wait_for_non_transient_printable_status(vm: VirtualMachineForTests, timeout: int = TIMEOUT_10MIN) -> str | None:
    """Wait until VM printableStatus is not a transient lifecycle state.

    Args:
        vm: VirtualMachine to poll.
        timeout: Sampler timeout in seconds.

    Returns:
        The settled printableStatus string.
    """
    LOGGER.info(f"Wait for non-transient printableStatus on VM {vm.name}")
    for sample in TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_5SEC,
        func=lambda: vm.printable_status,
    ):
        if sample is not None and sample not in _TRANSIENT_VM_STATUSES:
            return sample
    return None


def run_vm_action(
    vm: VirtualMachineForTests,
    vm_action: str,
    expected_exceptions: list[str] | None = None,
) -> None:
    """Run a VM lifecycle action once after printableStatus has settled.

    When expected_exceptions is set, either a matching ApiException or a
    successful call is accepted (strategies like Always/RerunOnFailure may
    reject or accept start depending on current state).

    Args:
        vm: VirtualMachine under test.
        vm_action: Name of the VirtualMachine method to call (start/restart/stop).
        expected_exceptions: Optional regex patterns; matching ApiException is OK.

    Raises:
        ApiException: On unexpected API errors that do not match expected_exceptions.
    """
    LOGGER.info(f"{vm_action} VM {vm.name}")
    wait_for_non_transient_printable_status(vm=vm)
    action = getattr(vm, vm_action)

    if expected_exceptions:
        try:
            action(wait=True, timeout=TIMEOUT_10MIN)
        except ApiException as error:
            if re.search(pattern=rf"{'|'.join(expected_exceptions)}", string=str(error)):
                return
            raise
        return

    action(wait=True, timeout=TIMEOUT_10MIN)


def verify_vm_ready_status(vm: VirtualMachineForTests, ready_status: bool | None = True) -> None:
    """Assert VM Ready condition and optionally wait until the guest is usable.

    Args:
        vm: VirtualMachine under test.
        ready_status: Expected Ready condition value; None means not Ready.
    """
    LOGGER.info(f"Verify VM ready status: {ready_status}")
    vm.wait_for_ready_status(status=ready_status, timeout=TIMEOUT_10MIN)
    if ready_status:
        wait_for_running_vm(vm=vm)


def verify_vm_run_strategy(vm: VirtualMachineForTests, run_strategy: str) -> None:
    """Assert VM spec.runStrategy matches the expected value.

    Args:
        vm: VirtualMachine under test.
        run_strategy: Expected runStrategy string.
    """
    LOGGER.info(f"Verify VM runStrategy: {run_strategy}")
    assert vm.instance.spec.runStrategy == run_strategy, (
        f"Expected runStrategy {run_strategy}, got {vm.instance.spec.runStrategy}"
    )


def verify_vm_action(vm: VirtualMachineForTests, vm_action: str, run_strategy: str) -> None:
    """Execute a lifecycle action and assert Ready status plus resulting runStrategy.

    Policy expectations come from RUN_STRATEGY_DICT for the given initial strategy.

    Args:
        vm: VirtualMachine under test.
        vm_action: Lifecycle action name (start, restart, or stop).
        run_strategy: Initial runStrategy used to look up expected outcomes.
    """
    run_strategy_policy = RUN_STRATEGY_DICT[run_strategy][vm_action]
    run_vm_action(
        vm=vm,
        vm_action=vm_action,
        expected_exceptions=run_strategy_policy.get("expected_exceptions"),
    )
    verify_vm_ready_status(vm=vm, ready_status=run_strategy_policy["status"])
    verify_vm_run_strategy(vm=vm, run_strategy=run_strategy_policy["run_strategy"])


def pause_unpause_vmi_and_verify_status(vm: VirtualMachineForTests) -> None:
    """Pause then unpause the VMI and assert the VM returns to Ready.

    Args:
        vm: VirtualMachine whose VMI is paused and unpaused.
    """
    vm.vmi.pause(wait=True)
    # vmi.pause waits on the VMI condition; printableStatus can lag behind
    vm.wait_for_specific_status(status=vm.Status.PAUSED)
    vm.vmi.unpause(wait=True)
    verify_vm_ready_status(vm=vm)


def migrate_validate_run_strategy_vm(
    vm: VirtualMachineForTests,
    client: DynamicClient,
    run_strategy: str,
) -> None:
    """Migrate a running VM and assert Ready status and runStrategy are unchanged.

    Args:
        vm: VirtualMachine to migrate.
        client: Kubernetes client used for migration verification.
        run_strategy: Expected runStrategy after migration.
    """
    LOGGER.info(f"The VM migration with runStrategy {run_strategy}")
    verify_vm_ready_status(vm=vm)
    migrate_vm_and_verify(vm=vm, client=client)
    verify_vm_ready_status(vm=vm)
    verify_vm_run_strategy(vm=vm, run_strategy=run_strategy)


def shutdown_vm_guest_os(vm: VirtualMachineForTests) -> None:
    """Power off the guest OS over SSH.

    Args:
        vm: VirtualMachine with SSH connectivity available.
    """
    LOGGER.info(f"Powering off {vm.name}")
    host = vm.ssh_exec
    host.sudo = True
    host.add_power_manager(pm_type=power_manager.SSH_TYPE)
    host.power_manager.poweroff()
