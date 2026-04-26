"""
Windows crash detection with hyperv panic device

Reference:
https://redhat.atlassian.net/browse/VIRTSTRAT-557
"""

import logging

import pytest
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError

from tests.os_params import WINDOWS_LATEST, WINDOWS_LATEST_LABELS
from utilities.constants import TIMEOUT_10SEC
from utilities.data_collector import collect_vnc_screenshot_for_vms
from utilities.virt import running_vm, vm_instance_from_template

pytestmark = [
    pytest.mark.special_infra,
    pytest.mark.high_resource_vm,
]

LOGGER = logging.getLogger(__name__)

BSOD_COMMAND = (
    "$e=$false; $r=0; "
    "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; "
    'public class C { [DllImport("ntdll.dll")] public static extern uint NtRaiseHardError'
    "(uint a,uint b,uint c,IntPtr d,uint e,out uint f); "
    '[DllImport("ntdll.dll")] public static extern uint RtlAdjustPrivilege'
    "(int a,bool b,bool c,out bool d);}'; "
    "[C]::RtlAdjustPrivilege(19,$true,$false,[ref]$e) | Out-Null; "
    "[C]::NtRaiseHardError([uint32]3221226528,0,0,[IntPtr]::Zero,6,[ref]$r)"
)


@pytest.fixture()
def windows_crashed(windows_vm_with_panic_device):
    LOGGER.info(f"Triggering BSOD on VM {windows_vm_with_panic_device.name} via NtRaiseHardError")
    try:
        run_ssh_commands(
            host=windows_vm_with_panic_device.ssh_exec,
            commands=["powershell", "-c", BSOD_COMMAND],
            timeout=TIMEOUT_10SEC,
        )
    except TimeoutError:
        LOGGER.info("SSH timeout as expected - VM has crashed")


def wait_for_guest_panicked_event(vm):
    LOGGER.info(f"Waiting for GuestPanicked event for VM {vm.name}")
    for event in vm.vmi.events(field_selector="reason==GuestPanicked"):
        LOGGER.info(f"GuestPanicked event found: {event}")
        return
    LOGGER.error(f"GuestPanicked event not found for VM {vm.name}")
    collect_vnc_screenshot_for_vms(vm=vm)
    raise TimeoutExpiredError("GuestPanicked event not received")


@pytest.fixture()
def windows_vm_with_panic_device(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_test_scope_function,
):
    vm_dict = {"spec": {"template": {"spec": {"domain": {"devices": {"panicDevices": [{"model": "hyperv"}]}}}}}}
    request.param["vm_dict"] = vm_dict

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_test_scope_function,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.parametrize(
    (
        "enabled_featuregate_scope_function, "
        "golden_image_data_source_for_test_scope_function, "
        "windows_vm_with_panic_device"
    ),
    [
        pytest.param(
            "PanicDevices",
            {"os_dict": WINDOWS_LATEST},
            {
                "vm_name": "windows-crash-detection-vm",
                "template_labels": WINDOWS_LATEST_LABELS,
            },
            marks=pytest.mark.polarion("CNV-15265"),
        ),
    ],
    indirect=True,
)
@pytest.mark.special_infra
@pytest.mark.high_resource_vm
def test_windows_crash_detection_with_hyperv_panic(
    enabled_featuregate_scope_function,
    windows_vm_with_panic_device,
    windows_crashed,
):
    """Test that KubeVirt detects Windows guest crash via Hyper-V panic device.

    Preconditions:
        - PanicDevices feature gate enabled
        - Windows VM created with hyperv panic device configured

    Steps:
        1. Trigger BSOD on Windows VM using NtRaiseHardError
        2. Wait for GuestPanicked event on VMI

    Expected:
        - VMI emits GuestPanicked event when Windows crashes
    """
    wait_for_guest_panicked_event(vm=windows_vm_with_panic_device)
