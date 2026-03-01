import json
import shlex

from kubernetes.dynamic import DynamicClient
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutSampler

from utilities.constants import HYPERV_FEATURES_LABELS_DOM_XML, TCP_TIMEOUT_30SEC, TIMEOUT_15SEC, TIMEOUT_90SEC
from utilities.virt import VirtualMachineForTests


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


def check_vm_xml_hyperv(vm: VirtualMachineForTests, admin_client: DynamicClient) -> None:
    """
    Verify HyperV values in VMI XML configuration.

    Args:
        vm (VirtualMachineForTests): Virtual machine instance to check for HyperV configuration.
        admin_client: Privileged client for XML dict access.

    Raises:
        AssertionError: If any HyperV flags are not set correctly in the VM spec, including:
            - Features from HYPERV_FEATURES_LABELS_DOM_XML not in "on" state
            - Spinlocks retries value not equal to 8191
            - Stimer direct feature not in "on" state
    """
    hyperv_features = vm.vmi.get_xml_dict(privileged_client=admin_client)["domain"]["features"]["hyperv"]
    failed_hyperv_features = [
        hyperv_features[feature]
        for feature in HYPERV_FEATURES_LABELS_DOM_XML
        if hyperv_features[feature]["@state"] != "on"
    ]
    spinlocks_retries_value = hyperv_features["spinlocks"]["@retries"]
    if int(spinlocks_retries_value) != 8191:
        failed_hyperv_features.append(spinlocks_retries_value)

    stimer_direct_feature = hyperv_features["stimer"]["direct"]
    if stimer_direct_feature["@state"] != "on":
        failed_hyperv_features.append(hyperv_features["stimer"])

    assert not failed_hyperv_features, (
        f"The following hyperV flags are not set correctly in VM spec: {failed_hyperv_features},"
        f"hyperV features in VM spec: {hyperv_features}"
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
