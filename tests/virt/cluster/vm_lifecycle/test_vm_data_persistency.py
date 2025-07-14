import logging
import random
import re
import shlex
import string

import pytest
from paramiko import ProxyCommandFailure
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import py_config
from timeout_sampler import TimeoutSampler

from tests.os_params import (
    RHEL_LATEST,
    RHEL_LATEST_LABELS,
    WINDOWS_LATEST,
    WINDOWS_LATEST_LABELS,
)
from utilities.constants import (
    OS_FLAVOR_RHEL,
    OS_FLAVOR_WINDOWS,
    TCP_TIMEOUT_30SEC,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_30MIN,
)
from utilities.ssp import get_windows_timezone
from utilities.virt import (
    vm_instance_from_template,
    wait_for_ssh_connectivity,
    wait_for_vm_interfaces,
)

LOGGER = logging.getLogger(__name__)


RHEL = OS_FLAVOR_RHEL
WIN = OS_FLAVOR_WINDOWS
NEW_TIMEZONE = {
    RHEL: "Antarctica/Troll",
    WIN: "New Zealand Standard Time",
}
NEW_FILENAME = "persistent_file"


@pytest.fixture(scope="module")
def vm_generated_new_password():
    return "".join(random.choice(f"{string.digits}{string.ascii_letters}$#!_-@") for index in range(15))


@pytest.fixture(scope="class")
def persistence_vm(request, golden_image_data_source_scope_class, unprivileged_client, namespace):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_class,
    ) as vm:
        yield vm


@pytest.fixture()
def changed_os_preferences(request, persistence_vm, vm_generated_new_password):
    os = request.param
    old_timezone = get_timezone(vm=persistence_vm, os=os)
    old_passwd = persistence_vm.password

    set_timezone(vm=persistence_vm, os=os, timezone=NEW_TIMEZONE[os])
    touch_file(vm=persistence_vm, os=os)
    set_passwd(vm=persistence_vm, os=os, passwd=vm_generated_new_password)

    yield

    LOGGER.info("Restore configuration")
    set_timezone(vm=persistence_vm, os=os, timezone=old_timezone)
    delete_file(vm=persistence_vm, os=os)
    set_passwd(vm=persistence_vm, os=os, passwd=old_passwd)


@pytest.fixture()
def restarted_persistence_vm(request, persistence_vm):
    restart_type = request.param["restart_type"]
    os = request.param["os"]

    if restart_type == "guest":
        guest_reboot(vm=persistence_vm, os=os)
    elif restart_type == "API":
        LOGGER.info(f"Rebooting {persistence_vm.name} from API")
        persistence_vm.restart(wait=True)

    # wait for the VM to come back up
    wait_for_vm_interfaces(vmi=persistence_vm.vmi)
    wait_for_ssh_connectivity(
        vm=persistence_vm,
        timeout=TIMEOUT_30MIN if os == WIN else TIMEOUT_5MIN,
        tcp_timeout=TIMEOUT_2MIN,
    )


def run_os_command(vm, command):
    try:
        return run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(command),
            timeout=5,
            tcp_timeout=TCP_TIMEOUT_30SEC,
        )[0]
    except ProxyCommandFailure:
        # On RHEL on successful reboot command execution ssh gets stuck
        if "reboot" not in command:
            raise


def wait_for_user_agent_down(vm, timeout):
    LOGGER.info(f"Waiting up to {round(timeout / 60)} minutes for user agent to go down on {vm.name}")
    for sample in TimeoutSampler(
        wait_timeout=timeout,
        sleep=2,
        func=lambda: [
            condition for condition in vm.vmi.instance.status.conditions if condition["type"] == "AgentConnected"
        ],
    ):
        if not sample:
            break


def get_linux_timezone(ssh_exec):
    return run_ssh_commands(host=ssh_exec, commands=shlex.split("timedatectl show | grep -i timezone"))[0]


def get_timezone(vm, os):
    tz = (
        get_linux_timezone(ssh_exec=vm.ssh_exec)
        if os == RHEL
        else get_windows_timezone(ssh_exec=vm.ssh_exec, get_standard_name=True)
    )

    # Outputs are different for RHEL/Windows, need to split differently
    # RHEL: 'Timezone=America/New_York\n'
    # Windows: 'StandardName               : New Zealand Standard Time\r\n'
    timezone = re.search(r".*[=|:][\s]?(.*?)[\r\n]", tz).group(1)
    LOGGER.info(f"Current timezone: {timezone}")
    return timezone


def set_timezone(vm, os, timezone):
    commands = {
        RHEL: f"sudo timedatectl set-timezone {timezone}",
        WIN: f"powershell -command \"Set-TimeZone -Id '{timezone}'\"",
    }

    LOGGER.info(f"Setting timezone: {timezone}")
    run_os_command(vm=vm, command=commands[os])

    LOGGER.info("Verifying timezone change")
    assert get_timezone(vm=vm, os=os) == timezone


def touch_file(vm, os):
    commands = {
        RHEL: f"touch {NEW_FILENAME}",
        WIN: f"echo > {NEW_FILENAME}",
    }

    LOGGER.info(f"Creating file: {NEW_FILENAME}")
    run_os_command(vm=vm, command=commands[os])

    LOGGER.info("Verifying file creation")
    assert grep_file(vm=vm, os=os)


def grep_file(vm, os):
    commands = {
        RHEL: f"ls | grep {NEW_FILENAME} ||true",
        WIN: f"dir | findstr {NEW_FILENAME} || ver>nul",
    }
    found_file = run_os_command(vm=vm, command=commands[os])
    return found_file


def delete_file(vm, os):
    commands = {RHEL: f"rm {NEW_FILENAME}", WIN: f"del {NEW_FILENAME}"}
    run_os_command(vm=vm, command=commands[os])
    assert not grep_file(vm=vm, os=os)


def set_passwd(vm, os, passwd):
    commands = {
        RHEL: f"echo {vm.username}:{passwd} | sudo chpasswd",
        WIN: f"net user {vm.username} {passwd}",
    }

    LOGGER.info(f"Setting password: {passwd}")
    run_os_command(vm=vm, command=commands[os])

    # Update the VM object password
    vm.password = passwd

    LOGGER.info("Verifying password change")
    vm.ssh_exec.executor().is_connective()


def guest_reboot(vm, os):
    commands = {
        "stop-user-agent": {
            RHEL: "sudo systemctl stop qemu-guest-agent",
            WIN: "powershell -command \"Stop-Service -Name 'QEMU-GA'\"",
        },
        "reboot": {
            RHEL: "sudo reboot",
            WIN: 'powershell -command "Restart-Computer -Force"',
        },
    }

    LOGGER.info("Stopping user agent")
    run_os_command(vm=vm, command=commands["stop-user-agent"][os])
    wait_for_user_agent_down(vm=vm, timeout=TIMEOUT_2MIN)

    LOGGER.info(f"Rebooting {vm.name} from guest")
    run_os_command(vm=vm, command=commands["reboot"][os])


def verify_changes(vm, os):
    # Verify passwd change and timezone
    # Password is verified by logging in using the new password
    assert get_timezone(vm=vm, os=os) == NEW_TIMEZONE[os]

    # verify touched file
    assert grep_file(vm=vm, os=os)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, persistence_vm",
    [
        [
            {
                "dv_name": "persistence-rhel-dv",
                "image": RHEL_LATEST["image_path"],
                "dv_size": RHEL_LATEST["dv_size"],
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "persistence-rhel-vm",
                "template_labels": RHEL_LATEST_LABELS,
            },
        ]
    ],
    indirect=True,
)
class TestRestartPersistenceLinux:
    @pytest.mark.parametrize(
        "changed_os_preferences, restarted_persistence_vm",
        [
            pytest.param(
                RHEL,
                {"restart_type": "guest", "os": RHEL},
                marks=pytest.mark.polarion("CNV-5618"),
                id="guest reboot",
            ),
            pytest.param(
                RHEL,
                {"restart_type": "API", "os": RHEL},
                marks=pytest.mark.polarion("CNV-5188"),
                id="API reboot",
            ),
        ],
        indirect=True,
    )
    def test_restart_persistence_linux(self, persistence_vm, changed_os_preferences, restarted_persistence_vm):
        verify_changes(vm=persistence_vm, os=RHEL)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, persistence_vm",
    [
        [
            {
                "dv_name": "persistence-windows-dv",
                "image": WINDOWS_LATEST.get("image_path"),
                "dv_size": WINDOWS_LATEST.get("dv_size"),
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "persistence-windows-vm",
                "template_labels": WINDOWS_LATEST_LABELS,
            },
        ]
    ],
    indirect=True,
)
@pytest.mark.special_infra
@pytest.mark.high_resource_vm
class TestRestartPersistenceWindows:
    @pytest.mark.parametrize(
        "changed_os_preferences, restarted_persistence_vm",
        [
            pytest.param(
                WIN,
                {"restart_type": "guest", "os": WIN},
                marks=pytest.mark.polarion("CNV-5617"),
                id="guest reboot",
            ),
            pytest.param(
                WIN,
                {"restart_type": "API", "os": WIN},
                marks=pytest.mark.polarion("CNV-5619"),
                id="API reboot",
            ),
        ],
        indirect=True,
    )
    def test_restart_persistence_windows(self, persistence_vm, changed_os_preferences, restarted_persistence_vm):
        verify_changes(vm=persistence_vm, os=WIN)
