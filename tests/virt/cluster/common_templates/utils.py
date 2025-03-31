import json
import logging
import re
import shlex
from datetime import datetime, timedelta, timezone

import bitmath
import pytest
from packaging import version
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.cluster.common_templates.constants import HYPERV_FEATURES_LABELS_DOM_XML
from utilities.constants import (
    OS_FLAVOR_RHEL,
    OS_FLAVOR_WINDOWS,
    TCP_TIMEOUT_30SEC,
    TIMEOUT_15SEC,
    TIMEOUT_90SEC,
)
from utilities.infra import (
    get_linux_guest_agent_version,
    get_linux_os_info,
    raise_multiple_exceptions,
    run_virtctl_command,
)
from utilities.ssp import get_windows_os_info
from utilities.virt import delete_guestosinfo_keys, get_virtctl_os_info

LOGGER = logging.getLogger(__name__)


def xfail_old_guest_agent_version(vm, ga_version):
    qemu_guest_agent_version = get_linux_guest_agent_version(ssh_exec=vm.ssh_exec)
    if version.parse(qemu_guest_agent_version.split()[0]) < version.parse(ga_version):
        pytest.xfail(reason=f"Bug in old guest agent version {qemu_guest_agent_version}")


def vm_os_version(vm):
    """Verify VM os version using SSH"""

    # Replace rhel with "redhat"
    os_name = "redhat" if OS_FLAVOR_RHEL in vm.os_flavor else vm.os_flavor
    os = re.search(r"(\w+-)?(\d+(-\d+)?)(-\d+-\d+)$", vm.name).group(2)
    command = shlex.split(f"cat /etc/{os_name}-release | grep {os.replace('-', '.')}")

    run_ssh_commands(host=vm.ssh_exec, commands=command)


def restart_qemu_guest_agent_service(vm):
    qemu_kvm_version = vm.privileged_vmi.virt_launcher_pod.execute(
        command=shlex.split("/usr/libexec/qemu-kvm --version | grep kvm"),
        container="compute",
    )
    qemu_guest_agent_version = get_linux_guest_agent_version(ssh_exec=vm.ssh_exec)
    if version.parse(qemu_kvm_version.split()[3]) >= version.parse("5.1.0") and version.parse(
        qemu_guest_agent_version
    ) >= version.parse("4.2.0-40"):
        return

    LOGGER.warning(
        f"Restart qemu-guest-agent service, qemu KVM version: {qemu_kvm_version},"
        f"qemu-guest-agent version: {qemu_guest_agent_version}"
    )
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split("sudo systemctl restart qemu-guest-agent"),
    )


# Guest agent data comparison functions.
def validate_os_info_virtctl_vs_linux_os(vm):
    def _get_os_info(vm):
        virtctl_info = get_virtctl_os_info(vm=vm)
        cnv_info = get_cnv_os_info(vm=vm)
        libvirt_info = get_libvirt_os_info(vm=vm)
        linux_info = get_linux_os_info(ssh_exec=vm.ssh_exec)
        return virtctl_info, cnv_info, libvirt_info, linux_info

    os_info_sampler = TimeoutSampler(wait_timeout=330, sleep=30, func=_get_os_info, vm=vm)
    check_guest_agent_sampler_data(sampler=os_info_sampler)


def validate_fs_info_virtctl_vs_linux_os(vm):
    def _get_fs_info(vm):
        virtctl_info = get_virtctl_fs_info(vm=vm)
        cnv_info = get_cnv_fs_info(vm=vm)
        libvirt_info = get_libvirt_fs_info(vm=vm)
        linux_info = get_linux_fs_info(ssh_exec=vm.ssh_exec)
        return virtctl_info, cnv_info, libvirt_info, linux_info

    orig_virtctl_info = cnv_info = libvirt_info = orig_linux_info = None

    fs_info_sampler = TimeoutSampler(wait_timeout=TIMEOUT_90SEC, sleep=1, func=_get_fs_info, vm=vm)

    try:
        for virtctl_info, cnv_info, libvirt_info, linux_info in fs_info_sampler:
            if virtctl_info:
                orig_virtctl_info = virtctl_info.copy()
                orig_linux_info = linux_info.copy()

                # Disk usage may not be bit exact; allowing up to 5% diff
                disk_usage_diff_validation = 1 - virtctl_info.pop("used") / linux_info.pop("used") <= 0.05
                if disk_usage_diff_validation and virtctl_info == linux_info:
                    return
    except TimeoutExpiredError as exp:
        raise_multiple_exceptions(
            exceptions=[
                ValueError(
                    f"Data mismatch!\nVirtctl: {orig_virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\n"
                    f"OS: {orig_linux_info}"
                ),
                exp,
            ]
        )


def validate_user_info_virtctl_vs_linux_os(vm):
    def _get_user_info(vm):
        virtctl_info = get_virtctl_user_info(vm=vm)
        cnv_info = get_cnv_user_info(vm=vm)
        libvirt_info = get_libvirt_user_info(vm=vm)
        linux_info = get_linux_user_info(ssh_exec=vm.ssh_exec)
        return virtctl_info, cnv_info, libvirt_info, linux_info

    user_info_sampler = TimeoutSampler(wait_timeout=30, sleep=10, func=_get_user_info, vm=vm)
    check_guest_agent_sampler_data(sampler=user_info_sampler)


def validate_os_info_virtctl_vs_windows_os(vm):
    virtctl_info = get_virtctl_os_info(vm=vm)
    cnv_info = get_cnv_os_info(vm=vm)
    libvirt_info = get_libvirt_os_info(vm=vm)
    windows_info = get_windows_os_info(ssh_exec=vm.ssh_exec)

    data_mismatch = []
    if version.parse(virtctl_info["guestAgentVersion"]) != version.parse(windows_info["guestAgentVersion"]):
        data_mismatch.append("GA version mismatch")
    if virtctl_info["hostname"] != windows_info["hostname"]:
        data_mismatch.append("hostname mismatch")
    if virtctl_info["timezone"].split(",")[0] not in windows_info["timezone"]:
        data_mismatch.append("timezone mismatch")
    for os_param_name, os_param_value in virtctl_info["os"].items():
        if os_param_value != windows_info["os"][os_param_name]:
            data_mismatch.append(f"OS data mismatch - {os_param_name}")

    assert not data_mismatch, (
        f"Data mismatch {data_mismatch}!"
        f"\nVirtctl: {virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\nOS: {windows_info}"
    )


def validate_fs_info_virtctl_vs_windows_os(vm):
    def _get_fs_info(vm):
        virtctl_info = get_virtctl_fs_info(vm=vm)
        cnv_info = get_cnv_fs_info(vm=vm)
        libvirt_info = get_libvirt_fs_info(vm=vm)
        windows_info = get_windows_fs_info(ssh_exec=vm.ssh_exec)
        return virtctl_info, cnv_info, libvirt_info, windows_info

    orig_virtctl_info = cnv_info = libvirt_info = orig_windows_info = None
    fs_info_sampler = TimeoutSampler(wait_timeout=TIMEOUT_90SEC, sleep=1, func=_get_fs_info, vm=vm)

    try:
        for virtctl_info, cnv_info, libvirt_info, windows_info in fs_info_sampler:
            if virtctl_info:
                orig_virtctl_info = virtctl_info.copy()
                orig_windows_info = windows_info.copy()

                # Disk usage may not be bit exact; allowing up to 10% diff (to allow deviation after conversion to GB)
                disk_usage_diff_validation = 1 - virtctl_info.pop("used") / windows_info.pop("used") <= 0.1
                if disk_usage_diff_validation and virtctl_info == windows_info:
                    return
    except TimeoutExpiredError as exp:
        raise_multiple_exceptions(
            exceptions=[
                ValueError(
                    f"Data mismatch!\nVirtctl: {orig_virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\n"
                    f"OS: {orig_windows_info}"
                ),
                exp,
            ]
        )


def validate_user_info_virtctl_vs_windows_os(vm):
    def _get_vm_timezone_diff():
        vm_timezone_diff = get_virtctl_os_info(vm=vm)["timezone"]
        # Get timezone diff from UTC
        # For example: 'Pacific Standard Time, -28800' -> return 28800
        return int(re.search(r".*, [-]?(\d+)", vm_timezone_diff).group(1))

    def _get_user_info_win(_vm):
        virtctl_info = get_virtctl_user_info(vm=vm)
        cnv_info = get_cnv_user_info(vm=vm)
        libvirt_info = get_libvirt_user_info(vm=vm)
        return virtctl_info, cnv_info, libvirt_info

    def _user_info_sampler_win(_vm):
        for sample in TimeoutSampler(wait_timeout=TIMEOUT_90SEC, sleep=10, func=_get_user_info_win, _vm=vm):
            if all(sample):
                return sample

    virtctl_info, cnv_info, libvirt_info = _user_info_sampler_win(_vm=vm)
    windows_info = run_ssh_commands(host=vm.ssh_exec, commands=["quser"], tcp_timeout=TCP_TIMEOUT_30SEC)[0]
    # Match timezone to VM's timezone and not use UTC
    virtctl_time = virtctl_info["loginTime"] - _get_vm_timezone_diff()
    data_mismatch = []
    if virtctl_info["userName"].lower() not in windows_info:
        data_mismatch.append("user name mismatch")
    # Windows date format - 11/4/2020 (-m/-d/Y)
    if datetime.utcfromtimestamp(virtctl_time).strftime("%-m/%-d/%Y") not in windows_info:
        data_mismatch.append("login time mismatch")

    assert not data_mismatch, (
        f"Data mismatch {data_mismatch}!"
        f"\nVirtctl: {virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\nOS: {windows_info}"
    )


def get_cnv_os_info(vm):
    """
    Returns OS data dict in format:
    {
        "guestAgentVersion": guestAgentVersion,
        "hostname": hostname,
        "os": {
            "name": name,
            "kernelRelease": kernelRelease,
            "version": version,
            "prettyName": prettyName,
            "versionId": versionId,
            "kernelVersion": kernelVersion,
            "machine": machine,
            "id": id,
        },
        "timezone": timezone",
    }
    """
    data = vm.vmi.guest_os_info
    return delete_guestosinfo_keys(data=data)


def get_libvirt_os_info(vm):
    agentinfo = execute_virsh_qemu_agent_command(vm=vm, command="guest-info")
    hostname = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-host-name")
    osinfo = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-osinfo")
    timezone = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-timezone")

    return {
        "guestAgentVersion": agentinfo["version"],
        "hostname": hostname["host-name"],
        "os": {
            "name": osinfo["name"],
            "kernelRelease": osinfo["kernel-release"],
            "version": osinfo["version"],
            "prettyName": osinfo["pretty-name"],
            "versionId": osinfo["version-id"],
            "kernelVersion": osinfo["kernel-version"],
            "machine": osinfo["machine"],
            "id": osinfo["id"],
        },
        "timezone": f"{timezone['zone']}, {timezone['offset']}",
    }


def get_virtctl_fs_info(vm):
    """
    Returns FS data dict in format:
    {
        "name": name,
        "mount": mount,
        "fsType": fsType,
        "used": <used bytes>,
        "total": <total bytes>,
    }
    """

    def _convert_bytes_to_gb(size):
        value = bitmath.Byte(bytes=size)
        return round(float(value.to_GB()))

    cmd = ["fslist", vm.name]
    res, output, err = run_virtctl_command(command=cmd, namespace=vm.namespace)
    if not res:
        LOGGER.error(f"Failed to get guest-agent info via virtctl. Error: {err}")
        return

    virtctl_info = guest_agent_disk_info_parser(disk_info=json.loads(output)["items"])

    if vm.os_flavor == OS_FLAVOR_WINDOWS:
        # For Windows, returned format is \\\\?\\Volume{ede1c0f3-0000-0000-0000-602200000000}\\
        virtctl_info["name"] = re.search(r".*Volume{(?P<name>.*)}.*", virtctl_info["name"])["name"]
        # Windows guest reports size in GB, virtctl in Byte
        virtctl_info["used"] = _convert_bytes_to_gb(size=virtctl_info["used"])
        virtctl_info["total"] = _convert_bytes_to_gb(size=virtctl_info["total"])

    return virtctl_info


def get_cnv_fs_info(vm):
    """
    Returns FS data dict in format:
    {
        "name": name,
        "mount": mount,
        "fsType": fsType,
        "used": <used bytes>,
        "total": <total bytes>,
    }
    """
    return guest_agent_disk_info_parser(disk_info=vm.vmi.guest_fs_info["items"])


def get_libvirt_fs_info(vm):
    """
    Returns FS data dict in format:
    {
        "name": name,
        "mount": mount,
        "fsType": fsType,
        "used": <used bytes>,
        "total": <total bytes>,
    }
    """
    fsinfo = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-fsinfo")
    return guest_agent_disk_info_parser(disk_info=fsinfo)


def get_linux_fs_info(ssh_exec):
    cmd = shlex.split("df -TB1 | grep /dev/vd")
    out = run_ssh_commands(host=ssh_exec, commands=cmd)[0]
    disks = out.strip().split()
    return {
        "name": disks[0].split("/dev/")[1],
        "mount": disks[6],
        "fsType": disks[1],
        "used": int(disks[3]),
        # ext3/4 FS reserves around 5% space for use by the root user; using used+available to calculate
        # total size without this buffer
        "total": int(disks[3]) + int(disks[4]),
    }


def get_windows_fs_info(ssh_exec):
    disk_name_cmd = shlex.split("fsutil volume list")
    disk_name = run_ssh_commands(host=ssh_exec, commands=disk_name_cmd, tcp_timeout=TCP_TIMEOUT_30SEC)[0]
    disk_space_cmd = shlex.split("fsutil volume diskfree C:")
    disk_space = (
        run_ssh_commands(host=ssh_exec, commands=disk_space_cmd, tcp_timeout=TCP_TIMEOUT_30SEC)[0].strip().split("\r\n")
    )
    fs_type_cmd = shlex.split("fsutil fsinfo volumeinfo C:")
    fs_type = run_ssh_commands(host=ssh_exec, commands=fs_type_cmd, tcp_timeout=TCP_TIMEOUT_30SEC)[0]

    windows_info = f"{disk_name} {windows_disk_space_parser(disk_space)} {fs_type}"
    windows_fs_info = re.search(
        r".*Volume{(?P<name>.*)}.*(?P<mount>[a-zA-Z]:\\).*used "
        r"(?P<used>\d+),.*total (?P<total>\d+).*File System Name : "
        r"(?P<fsType>[a-zA-Z]+).*",
        windows_info,
        re.DOTALL,
    ).groupdict()

    # Cast 'used' and 'total' to int
    windows_fs_info = {
        **windows_fs_info,
        "total": int(windows_fs_info["total"]),
        "used": int(windows_fs_info["used"]),
    }

    return windows_fs_info


def get_virtctl_user_info(vm):
    cmd = ["userlist", vm.name]
    res, output, err = run_virtctl_command(command=cmd, namespace=vm.namespace)
    if not res:
        LOGGER.error(f"Failed to get guest-agent info via virtctl. Error: {err}")
        return
    for user in json.loads(output)["items"]:
        return {
            "userName": user["userName"],
            "loginTime": int(user["loginTime"]),
        }


def get_cnv_user_info(vm):
    for user in vm.vmi.guest_user_info["items"]:
        return {
            "userName": user["userName"],
            "loginTime": int(user["loginTime"]),
        }


def get_libvirt_user_info(vm):
    userinfo = execute_virsh_qemu_agent_command(vm=vm, command="guest-get-users")
    for user in userinfo:
        return {
            "userName": user["user"],
            "loginTime": int(user["login-time"]),
        }


def get_linux_user_info(ssh_exec):
    cmd = shlex.split("lastlog | grep tty; who | awk \"'{print$3}'\"")
    out = run_ssh_commands(host=ssh_exec, commands=cmd)[0]
    users = out.strip().split()
    date = datetime.strptime(f"{users[7]}-{users[3]}-{users[4]} {users[5]}", "%Y-%b-%d %H:%M:%S")
    timestamp = date.replace(tzinfo=timezone(timedelta(seconds=int(ssh_exec.os.timezone.offset) * 36))).timestamp()
    return {
        "userName": users[0],
        "loginTime": int(timestamp),
    }


# Guest agent test related functions.
def guest_agent_disk_info_parser(disk_info):
    for disk in disk_info:
        if disk.get("mountpoint", disk.get("mountPoint")) in ("/", "C:\\"):
            return {
                "name": disk.get("name", disk.get("diskName")),
                "mount": disk.get("mountpoint", disk.get("mountPoint")),
                "fsType": disk.get("type", disk.get("fileSystemType")),
                "used": disk.get("used-bytes", disk.get("usedBytes")),
                "total": disk.get("total-bytes", disk.get("totalBytes")),
            }


def windows_disk_space_parser(fsinfo_list):
    # fsinfo_list contains strings of total free and total bytes in format:
    # ['Total free bytes        :  81,103,310,848 ( 75.5 GB)',
    #  'Total bytes             : 249,381,777,408 (232.3 GB)',
    #  'Total quota free bytes  :  81,103,310,848 ( 75.5 GB)']
    disk_space = {
        "total": re.sub(",", "", re.search(r":\s+([\d,]+)", fsinfo_list[1]).group(1)),
        "free": re.sub(",", "", re.search(r":\s+([\d,]+)", fsinfo_list[0]).group(1)),
    }
    used = round((int(disk_space["total"]) - int(disk_space["free"])) / 1000**3)
    total = round(int(disk_space["total"]) / 1000**3)
    return f"used {used}, total {total}\n"


def execute_virsh_qemu_agent_command(vm, command):
    domain = f"{vm.namespace}_{vm.vmi.name}"
    output = vm.privileged_vmi.virt_launcher_pod.execute(
        command=["virsh", "qemu-agent-command", domain, f'{{"execute":"{command}"}}'],
        container="compute",
    )
    return json.loads(output)["return"]


def check_guest_agent_sampler_data(sampler):
    virtctl_info = cnv_info = libvirt_info = linux_info = None
    try:
        for virtctl_info, cnv_info, libvirt_info, linux_info in sampler:
            if virtctl_info:
                if virtctl_info == linux_info:
                    return
    except TimeoutExpiredError as exp:
        raise_multiple_exceptions(
            exceptions=[
                ValueError(
                    f"Data mismatch!\nVirtctl: {virtctl_info}\nCNV: {cnv_info}\nLibvirt: {libvirt_info}\n"
                    f"OS: {linux_info}"
                ),
                exp,
            ]
        )


def check_machine_type(vm):
    """VM and VMI should have machine type; machine type cannot be empty"""

    vm_machine_type = vm.instance.spec.template.spec.domain.machine.type
    vmi_machine_type = vm.vmi.instance.spec.domain.machine.type

    assert vm_machine_type == vmi_machine_type, (
        f"VM and VMI machine type do not match. VM: {vm_machine_type}, VMI: {vmi_machine_type}"
    )

    assert vm_machine_type != "", f"Machine type does not exist in VM: {vm_machine_type}"


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


def check_vm_xml_clock(vm):
    """Verify clock values in VMI"""

    clock_timer_list = vm.privileged_vmi.xml_dict["domain"]["clock"]["timer"]
    assert [i for i in clock_timer_list if i["@name"] == "hpet"][0]["@present"] == "no"
    assert [i for i in clock_timer_list if i["@name"] == "hypervclock"][0]["@present"] == "yes"


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
            failed_recommendations.append(failed_vm_recommendations)

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
        failed_windows_hyperv_list.extend("HyperVsupport")

    assert not failed_windows_hyperv_list, (
        f"The following hyperV flags are not set correctly in the guest: {failed_windows_hyperv_list}\n"
        f"VM hvinfo dict:{hvinfo_dict}"
    )


def set_vm_tablet_device_dict(tablet_params):
    """Generates VM tablet device dict"""

    return {"spec": {"template": {"spec": {"domain": {"devices": {"inputs": [tablet_params]}}}}}}


def check_vm_xml_tablet_device(vm):
    """Verifies vm tablet device info in VM XML vs VM instance attributes
    values.
    """

    LOGGER.info("Verify VM XML - tablet device values.")

    vm_instance_tablet_device_dict = vm.instance["spec"]["template"]["spec"]["domain"]["devices"]["inputs"][0]

    tablet_dict_from_xml = [
        i for i in vm.privileged_vmi.xml_dict["domain"]["devices"]["input"] if i["@type"] == "tablet"
    ][0]

    assert tablet_dict_from_xml["@type"] == vm_instance_tablet_device_dict["type"], "Wrong device type"

    # Default bus type is usb; not added to the VM instance if it was not
    # specified during VM creation.
    assert tablet_dict_from_xml["@bus"] == vm_instance_tablet_device_dict.get("bus", "usb"), "Wrong bus type"
    assert tablet_dict_from_xml["alias"]["@name"] == f"ua-{vm_instance_tablet_device_dict['name']}", "Wrong device name"


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
