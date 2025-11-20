import json
import shlex

from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutSampler

from utilities.constants import HYPERV_FEATURES_LABELS_DOM_XML, TCP_TIMEOUT_30SEC, TIMEOUT_15SEC, TIMEOUT_90SEC


def assert_windows_efi(vm):
    """
    Verify guest OS is using EFI.
    """
    out = run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split("bcdedit | findstr EFI"),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )[0]
    assert "\\EFI\\Microsoft\\Boot\\bootmgfw.efi" in out, f"EFI boot not found in path. bcdedit output:\n{out}"


def check_vm_xml_hyperv(vm):
    """Verify HyperV values in VMI"""

    hyperv_features = vm.privileged_vmi.xml_dict["domain"]["features"]["hyperv"]
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


def check_windows_vm_hvinfo(vm):
    """Verify HyperV values in Windows VMI using hvinfo"""

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

    failed_windows_hyperv_list = _check_hyperv_recommendations()
    failed_windows_hyperv_list.extend(_check_hyperv_privileges())
    failed_windows_hyperv_list.extend(_check_hyperv_features())

    if not hvinfo_dict["HyperVsupport"]:
        failed_windows_hyperv_list.append("HyperVsupport")

    assert not failed_windows_hyperv_list, (
        f"The following hyperV flags are not set correctly in the guest: {failed_windows_hyperv_list}\n"
        f"VM hvinfo dict:{hvinfo_dict}"
    )
