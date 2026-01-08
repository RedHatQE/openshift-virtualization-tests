from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ocp_resources.virtual_machine import VirtualMachine
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.scale.constants import GUEST_DATA_COMMAND_LIST, GUEST_DATA_RESULT_SEPARATOR
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_2MIN, TIMEOUT_4MIN, TIMEOUT_8MIN, TIMEOUT_10SEC
from utilities.virt import (
    VirtualMachineForTests,
    wait_for_cloud_init_complete,
    wait_for_running_vm,
    wait_for_ssh_connectivity,
)

LOGGER = logging.getLogger(__name__)


def threaded_wait_for_accessible_vms(
    vms: list[VirtualMachineForTests],
    timeout: int = TIMEOUT_2MIN,
    tcp_timeout: int = TIMEOUT_1MIN,
    sleep: int = TIMEOUT_10SEC,
) -> None:  # skip-unused-code
    """
    Asynchronously wait for accessible VMs

    Args:
        vms (list[VirtualMachineForTests]): List of VMs to wait for
        timeout (int): Timeout to wait for SSH connectivity
        tcp_timeout (int): TCP timeout
        sleep (int): Sleep between checks
    """
    assert vms, f"No VMs provided {vms!r}"

    def _wait_for_accessible_vm(_vm: VirtualMachineForTests) -> None:
        wait_for_ssh_connectivity(vm=_vm, timeout=timeout, tcp_timeout=tcp_timeout, sleep=sleep)

    with ThreadPoolExecutor(max_workers=len(vms)) as executor:
        list(executor.map(_wait_for_accessible_vm, vms))


def threaded_wait_for_running_vms(
    vms: list[VirtualMachineForTests],
    wait_for_interfaces: bool = False,
    check_ssh_connectivity: bool = False,
    wait_for_cloud_init: bool = False,
    wait_until_running_timeout: int = TIMEOUT_8MIN,
    ssh_timeout: int = TIMEOUT_4MIN,
    cloud_init_timeout: int = TIMEOUT_8MIN,
) -> list[Any]:  # skip-unused-code
    """
    Asynchronously wait for running VMs

    Args:
        vms (list): List of VirtualMachines
        wait_for_interfaces (bool): Wait for VM interfaces
        check_ssh_connectivity (bool): Check for SSH connectivity
        wait_for_cloud_init (bool, optional): Wait for VM cloud-init completion
        wait_until_running_timeout (int): Time to wait until running
        ssh_timeout (int): SSH Timeout
        cloud_init_timeout (int): Time to wait for cloud init

    Returns:
        list: Data related to the running of the async function
    """
    assert vms, f"No VMs provided {vms!r}"

    def _wait_running_vm(_vm: VirtualMachineForTests) -> None:
        try:
            wait_for_running_vm(
                vm=_vm,
                wait_for_interfaces=wait_for_interfaces,
                check_ssh_connectivity=check_ssh_connectivity,
                wait_until_running_timeout=wait_until_running_timeout,
                ssh_timeout=ssh_timeout,
            )
        except TimeoutExpiredError:
            LOGGER.error(f"VM: {_vm.name} Status: {_vm.instance.status}")
            raise

        if wait_for_cloud_init:
            wait_for_cloud_init_complete(vm=_vm, timeout=cloud_init_timeout)

    with ThreadPoolExecutor(max_workers=len(vms)) as executor:
        return list(executor.map(_wait_running_vm, vms))


def threaded_wait_for_scheduled_vms(
    vms: list[VirtualMachine], wait_timeout=TIMEOUT_8MIN
) -> list[Any]:  # skip-unused-code
    """
    Asynchronously wait for scheduled VMs

    Args:
        vms (list): List of VirtualMachines
        wait_timeout (int): Time to wait for a single VM to be scheduled

    Returns:
        list: Data related to the running of the async function
    """
    assert vms, f"No VMs provided {vms!r}"

    def _wait_for_scheduled_vm(_vm: VirtualMachine) -> None:
        def _get_virt_launcher_instance():
            virt_launcher_pod = _vm.vmi.virt_launcher_pod
            if virt_launcher_pod:
                return virt_launcher_pod.exists

        sampler = TimeoutSampler(
            wait_timeout=wait_timeout,
            sleep=1,
            func=_get_virt_launcher_instance,
        )
        try:
            sample = None
            for sample in sampler:
                if sample and sample.spec.nodeName:
                    return
        except TimeoutExpiredError:
            LOGGER.error(f"VM: {_vm.name} Status: {_vm.instance.status} virt-launcher: {sample}")

            raise

    with ThreadPoolExecutor(max_workers=len(vms)) as executor:
        return list(executor.map(_wait_for_scheduled_vm, vms))


def threaded_run_vm_ssh_command(
    vms: list[VirtualMachineForTests], commands: list[str], tcp_timeout=TIMEOUT_8MIN
) -> list:  # skip-unused-code
    """
    Asynchronously run SSH commands on VMs

    Args:
        vms (list): List of VirtualMachines
        commands (list[str]): Commands to run
        tcp_timeout (int): TCP timeout

    Returns:
        list: Data related to the running of the async function
    """
    assert vms, f"No VMs provided {vms!r}"

    def _run_ssh_commands(_vm: VirtualMachineForTests) -> list:
        return run_ssh_commands(
            host=_vm.ssh_exec,
            commands=commands,
            tcp_timeout=tcp_timeout,
        )

    with ThreadPoolExecutor(max_workers=len(vms)) as executor:
        return list(executor.map(_run_ssh_commands, vms))


def threaded_get_vm_guest_data(vms: list[VirtualMachineForTests], commands: list[str]) -> list[Any]:  # skip-unused-code
    """
    Asynchronously run commands from GUEST_DATA_COMMAND_LIST in VMs to pull guest data

    Args:
        vms (list): List of VirtualMachines
        commands (list[str]): Commands to run from GUEST_DATA_COMMAND_LIST

    Returns:
        list: Data related to the running of the async function
    """
    assert vms, f"No VMs provided {vms!r}"
    result = threaded_run_vm_ssh_command(vms=vms, commands=commands)
    all_guest_data = []
    for idx, entry in enumerate(result):
        vm = vms[idx]
        command_call_result_list = entry[0].strip().split(GUEST_DATA_RESULT_SEPARATOR)

        entry_data = {}
        for cmd_idx, call_result in enumerate(command_call_result_list):
            command_call_info = GUEST_DATA_COMMAND_LIST[cmd_idx]
            regex: re.Pattern = command_call_info["regex"]
            data_match = regex.match(string=call_result.strip())
            if data_match:
                entry_data.update(data_match.groupdict())
            else:
                raise ValueError(
                    f"VM {vm.namespace} {vm.name}: Regex does not match call result: {regex.pattern!r} {call_result!r}"
                )

        all_guest_data.append(entry_data)

    return all_guest_data


def verify_guest_data(data_before_action: dict, data_after_action: dict) -> None:  # skip-unused-code
    """
    Verify data gathered using GUEST_DATA_COMMAND_LIST before and after an event or action

    Args:
        data_before_action (dict): Data before event or action
        data_after_action (dict): Data after event or action
    """
    return_errors = []

    if not (data_before_action and data_after_action and data_before_action != data_after_action):
        raise ValueError(f"invalid input: before:{data_before_action!r} after:{data_after_action!r}")

    for name in data_before_action:
        if name == "datetime":
            if data_before_action[name] >= data_after_action[name]:
                return_errors.append(
                    "Before datetime is not before after datetime. "
                    "before: {data_before_action[name]} after: {data_after_action[name]}"
                )
        elif name == "btime":
            if data_before_action[name] != data_after_action[name]:
                return_errors.append(
                    f"Boot times do not match. before: {data_before_action[name]} after: {data_after_action[name]}"
                )

    assert not return_errors, return_errors


def threaded_verify_guest_data(
    data_before_action_list: list[dict], data_after_action_list: list[dict]
) -> None:  # skip-unused-code
    """
    Threaded verify data gathered using GUEST_DATA_COMMAND_LIST from multiple VMs before and after an event or action

    Args:
        data_before_action_list (list[dict]): List of data before event or action
        data_after_action_list (list[dict]): List of data after event or action
    """
    before_list_length = len(data_before_action_list)
    assert data_before_action_list and data_after_action_list and before_list_length == len(data_after_action_list), (
        "Guest data lists must be provided and be of equal length"
    )
    with ThreadPoolExecutor(max_workers=before_list_length) as executor:
        list(executor.map(verify_guest_data, data_before_action_list, data_after_action_list))
