from __future__ import annotations

import json
import logging
import shlex
from typing import TYPE_CHECKING

from kubernetes.dynamic import DynamicClient
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutSampler

from utilities.constants.timeouts import (
    TCP_TIMEOUT_30SEC,
    TIMEOUT_15SEC,
    TIMEOUT_90SEC,
)
from utilities.constants.virt import OS_PROC_NAME
from utilities.virt import (
    VirtualMachineForTests,
    fetch_pid_from_windows_vm,
    pause_unpause_vm_and_check_connectivity,
    start_and_fetch_processid_on_windows_vm,
)

if TYPE_CHECKING:
    from typing import Any

LOGGER = logging.getLogger(__name__)

YAML_TO_XML_FEATURE_NAMES: dict[str, str] = {
    "synictimer": "stimer",
}

SPINLOCKS_EXPECTED_RETRIES = 8191


def assert_windows_efi(vm: VirtualMachineForTests) -> None:
    """
    Verify guest OS is using EFI.

    Args:
        vm (VirtualMachineForTests): Virtual machine instance to check for EFI boot.

    Raises:
        AssertionError: If EFI boot path is not found in the bcdedit output.
    """
    out = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split("bcdedit | findstr EFI"),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )[0]
    assert "\\EFI\\Microsoft\\Boot\\bootmgfw.efi" in out, f"EFI boot not found in path. bcdedit output:\n{out}"


def _collect_hyperv_feature_failures(
    expected_features: dict[str, Any],
    actual_features: dict[str, Any],
) -> list[str]:
    """Compare expected hyperv features against actual VMI XML features.

    Walks the expected features dict (VM yaml format) and verifies each feature
    and its sub-features have ``@state == "on"`` in the actual XML. For spinlocks,
    also verifies the retries value matches.

    Args:
        expected_features: Expected hyperv features dict in VM yaml format.
            Feature names are automatically mapped from yaml to XML naming
            (e.g., synictimer → stimer).
        actual_features: Actual hyperv features dict from VMI XML.

    Returns:
        List of failure descriptions for features not matching expected state.
    """
    failures: list[str] = []

    for yaml_name, expected_value in expected_features.items():
        xml_name = YAML_TO_XML_FEATURE_NAMES.get(yaml_name, yaml_name)

        if xml_name not in actual_features:
            failures.append(f"Feature '{xml_name}' not found in VM XML")
            continue

        actual_feature = actual_features[xml_name]

        if actual_feature.get("@state") != "on":
            failures.append(f"Feature '{xml_name}' state is '{actual_feature.get('@state')}', expected 'on'")

        if xml_name == "spinlocks":
            expected_retries = (
                expected_value.get("spinlocks", SPINLOCKS_EXPECTED_RETRIES)
                if isinstance(expected_value, dict)
                else SPINLOCKS_EXPECTED_RETRIES
            )
            actual_retries = int(actual_feature.get("@retries", 0))
            if actual_retries != expected_retries:
                failures.append(f"Spinlocks retries is {actual_retries}, expected {expected_retries}")

        if isinstance(expected_value, dict):
            for sub_name, sub_value in expected_value.items():
                if not isinstance(sub_value, dict):
                    continue

                if sub_name not in actual_feature:
                    failures.append(f"Sub-feature '{xml_name}.{sub_name}' not found in VM XML")
                    continue

                if actual_feature[sub_name].get("@state") != "on":
                    failures.append(
                        f"Sub-feature '{xml_name}.{sub_name}' state is"
                        f" '{actual_feature[sub_name].get('@state')}', expected 'on'"
                    )

    return failures


def check_vm_xml_hyperv(
    vm: VirtualMachineForTests,
    admin_client: DynamicClient,
    expected_hyperv_features: dict[str, Any],
) -> None:
    """Verify HyperV values in VMI XML configuration.

    Compares the expected hyperv features against the actual VMI XML. Each listed
    feature and its sub-features are verified to have ``@state == "on"``, and
    spinlocks retries are validated.

    Args:
        vm: Virtual machine instance to check for HyperV configuration.
        admin_client: Privileged client for XML dict access.
        expected_hyperv_features: Expected hyperv features dict in VM yaml format.
            Keys are feature names (e.g., "relaxed", "synictimer"), values are dicts
            of sub-features (e.g., ``{"direct": {}}``). Feature names are automatically
            mapped from yaml to XML naming (synictimer → stimer).

    Raises:
        AssertionError: If any HyperV flags are not set correctly in the VM spec.
    """
    hyperv_features = vm.vmi.get_xml_dict(privileged_client=admin_client)["domain"]["features"]["hyperv"]
    failures = _collect_hyperv_feature_failures(
        expected_features=expected_hyperv_features,
        actual_features=hyperv_features,
    )
    assert not failures, (
        f"The following hyperV flags are not set correctly in VM spec: {failures},"
        f" hyperV features in VM spec: {hyperv_features}"
    )


def check_windows_vm_hvinfo(vm: VirtualMachineForTests) -> None:
    """
    Verify HyperV values in Windows VM using hvinfo.exe tool.

    Args:
        vm (VirtualMachineForTests): Virtual machine instance running Windows guest OS.

    Raises:
        AssertionError: If any HyperV flags are not set correctly in the guest, including:
            - Missing HyperV recommendations (RelaxedTiming, MSRAPICRegisters, etc.)
            - Incorrect spinlock retries value (not 8191)
            - Missing HyperV privileges (AccessVpRunTimeReg, AccessSynicRegs, etc.)
            - Missing HyperV features (TimerFrequenciesQuery)
            - HyperVsupport flag not enabled
        TimeoutExpiredError: If hvinfo.exe output cannot be retrieved within the timeout period.
    """

    def _check_hyperv_recommendations():
        hyperv_windows_recommendations_list = [
            "RelaxedTiming",
            "MSRAPICRegisters",
            "HypercallRemoteTLBFlush",
            "SyntheticClusterIPI",
        ]
        failed_recommendations = []
        vm_recommendations_dict = hvinfo_dict["Recommendations"]
        failed_vm_recommendations = [
            feature for feature in hyperv_windows_recommendations_list if not vm_recommendations_dict[feature]
        ]

        if failed_vm_recommendations:
            failed_recommendations.extend(failed_vm_recommendations)

        spinlocks = vm_recommendations_dict["SpinlockRetries"]
        if int(spinlocks) != 8191:
            failed_recommendations.append(f"SpinlockRetries: {spinlocks}")

        return failed_recommendations

    def _check_hyperv_privileges():
        hyperv_windows_privileges_list = [
            "AccessVpRunTimeReg",
            "AccessSynicRegs",
            "AccessSyntheticTimerRegs",
            "AccessVpIndex",
        ]
        vm_privileges_dict = hvinfo_dict["Privileges"]
        return [feature for feature in hyperv_windows_privileges_list if not vm_privileges_dict[feature]]

    def _check_hyperv_features():
        hyperv_windows_features_list = ["TimerFrequenciesQuery"]
        vm_features_dict = hvinfo_dict["Features"]
        return [feature for feature in hyperv_windows_features_list if not vm_features_dict[feature]]

    hvinfo_dict = None

    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_90SEC,
        sleep=TIMEOUT_15SEC,
        func=run_ssh_commands,
        host=vm.ssh_exec,
        commands=["C:\\\\hvinfo\\\\hvinfo.exe"],
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )
    for sample in sampler:
        output = sample[0]
        if output and "connect: connection refused" not in output:
            hvinfo_dict = json.loads(output)
            break

    assert hvinfo_dict is not None, "Failed to retrieve hvinfo output from Windows VM"
    failed_windows_hyperv_list = _check_hyperv_recommendations()
    failed_windows_hyperv_list.extend(_check_hyperv_privileges())
    failed_windows_hyperv_list.extend(_check_hyperv_features())

    if not hvinfo_dict["HyperVsupport"]:
        failed_windows_hyperv_list.append("HyperVsupport")

    assert not failed_windows_hyperv_list, (
        f"The following hyperV flags are not set correctly in the guest: {failed_windows_hyperv_list}\n"
        f"VM hvinfo dict:{hvinfo_dict}"
    )


def validate_pause_unpause_windows_vm(vm: VirtualMachineForTests, pre_pause_pid: int | None = None) -> None:
    proc_name = OS_PROC_NAME["windows"]
    if pre_pause_pid is None:
        pre_pause_pid = start_and_fetch_processid_on_windows_vm(vm=vm, process_name=proc_name)
    pause_unpause_vm_and_check_connectivity(vm=vm)
    post_pause_pid = fetch_pid_from_windows_vm(vm=vm, process_name=proc_name)
    kill_processes_by_name_windows(vm=vm, process_name=proc_name)
    assert post_pause_pid == pre_pause_pid, (
        f"PID mismatch!\nPre pause PID is: {pre_pause_pid}\nPost pause PID is: {post_pause_pid}"
    )


def kill_processes_by_name_windows(vm: VirtualMachineForTests, process_name: str) -> None:
    cmd = shlex.split(f"taskkill /F /IM {process_name}")
    run_ssh_commands(host=vm.ssh_exec, commands=cmd, tcp_timeout=TCP_TIMEOUT_30SEC)
