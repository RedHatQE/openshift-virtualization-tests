import ast
import shlex

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pyhelper_utils.shell import run_ssh_commands

from tests.storage.snapshots.constants import ERROR_MSG_USER_CANNOT_CREATE_VM_SNAPSHOTS
from utilities.constants import TIMEOUT_10MIN
from utilities.virt import running_vm


def expected_output_after_restore(snapshot_number):
    """
    Returns a string representing the list of files that should exist in the VM (sorted)
    after a restore snapshot was performed

    Args:
        snapshot_number (int): The snapshot number that was restored

    Returns:
        string: the list of files that should exist on the VM after restore operation was performed
    """
    files = []
    for idx in range(snapshot_number - 1):
        files.append(f"before-snap-{idx + 1}.txt")
        files.append(f"after-snap-{idx + 1}.txt")
    files.append(f"before-snap-{snapshot_number}.txt ")
    files.sort()
    return " ".join(files)


def fail_to_create_snapshot_no_permissions(snapshot_name, namespace, vm_name, client):
    with pytest.raises(
        ApiException,
        match=ERROR_MSG_USER_CANNOT_CREATE_VM_SNAPSHOTS,
    ):
        with VirtualMachineSnapshot(
            name=snapshot_name,
            namespace=namespace,
            vm_name=vm_name,
            client=client,
        ):
            return


def assert_directory_existence(expected_result, windows_vm, directory_path):
    cmd = shlex.split(f'powershell -command "Test-Path -Path {directory_path}"')
    out = run_ssh_commands(host=windows_vm.ssh_exec, commands=cmd)[0].strip()
    assert expected_result == ast.literal_eval(out), f"Directory exist: {out}, expected result: {expected_result}"


def start_windows_vm_after_restore(vm_restore, windows_vm):
    vm_restore.wait_restore_done(timeout=TIMEOUT_10MIN)
    running_vm(vm=windows_vm)


def run_command_on_vm_and_check_output(vm, command, expected_result):
    """Run command on RHEL VM via SSH and verify expected result is in output.

    Args:
        vm (VirtualMachineForTests): VM to run command on.
        command (str): Command to run.
        expected_result (str): Expected result to check.

    Raises:
        AssertionError: If expected result is not in output.
    """
    cmd_output = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"bash -c {shlex.quote(command)}"),
    )[0].strip()
    expected_result = expected_result.strip()
    assert expected_result in cmd_output, f"Expected '{expected_result}' in output '{cmd_output}'"
