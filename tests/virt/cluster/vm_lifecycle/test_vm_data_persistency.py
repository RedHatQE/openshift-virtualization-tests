import logging
import random
import re
import shlex
import string

import pytest
from pyhelper_utils.shell import run_ssh_commands

from tests.os_params import (
    RHEL_LATEST,
    RHEL_LATEST_LABELS,
    WINDOWS_LATEST,
    WINDOWS_LATEST_LABELS,
)
from utilities.constants import (
    LINUX_STR,
    OS_FLAVOR_RHEL,
    OS_FLAVOR_WINDOWS,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_30MIN,
)
from utilities.ssp import get_windows_timezone
from utilities.virt import (
    guest_reboot,
    run_os_command,
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
def persistence_vm(request, golden_image_data_volume_template_for_test_scope_class, unprivileged_client, namespace):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_test_scope_class,
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
    os_type = request.param["os_type"]

    if restart_type == "guest":
        guest_reboot(vm=persistence_vm, os_type=os_type)
    elif restart_type == "API":
        LOGGER.info(f"Rebooting {persistence_vm.name} from API")
        persistence_vm.restart(wait=True)

    # wait for the VM to come back up
    wait_for_vm_interfaces(vmi=persistence_vm.vmi)
    wait_for_ssh_connectivity(
        vm=persistence_vm,
        timeout=TIMEOUT_30MIN if os_type == WIN else TIMEOUT_5MIN,
        tcp_timeout=TIMEOUT_2MIN,
    )


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


def verify_changes(vm, os):
    # Verify passwd change and timezone
    # Password is verified by logging in using the new password
    assert get_timezone(vm=vm, os=os) == NEW_TIMEZONE[os]

    # verify touched file
    assert grep_file(vm=vm, os=os)


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class, persistence_vm",
    [
        [
            {"os_dict": RHEL_LATEST},
            {"vm_name": "persistence-rhel-vm", "template_labels": RHEL_LATEST_LABELS},
        ]
    ],
    indirect=True,
)
class TestRestartPersistenceLinux:
    @pytest.mark.s390x
    @pytest.mark.parametrize(
        "changed_os_preferences, restarted_persistence_vm",
        [
            pytest.param(
                RHEL,
                {"restart_type": "guest", "os_type": LINUX_STR},
                marks=pytest.mark.polarion("CNV-5618"),
                id="guest reboot",
            ),
            pytest.param(
                RHEL,
                {"restart_type": "API", "os_type": LINUX_STR},
                marks=pytest.mark.polarion("CNV-5188"),
                id="API reboot",
            ),
        ],
        indirect=True,
    )
    def test_restart_persistence_linux(self, persistence_vm, changed_os_preferences, restarted_persistence_vm):
        verify_changes(vm=persistence_vm, os=RHEL)


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class, persistence_vm",
    [
        [
            {"os_dict": WINDOWS_LATEST},
            {"vm_name": "persistence-windows-vm", "template_labels": WINDOWS_LATEST_LABELS},
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
                {"restart_type": "guest", "os_type": WIN},
                marks=pytest.mark.polarion("CNV-5617"),
                id="guest reboot",
            ),
            pytest.param(
                WIN,
                {"restart_type": "API", "os_type": WIN},
                marks=pytest.mark.polarion("CNV-5619"),
                id="API reboot",
            ),
        ],
        indirect=True,
    )
    def test_restart_persistence_windows(self, persistence_vm, changed_os_preferences, restarted_persistence_vm):
        verify_changes(vm=persistence_vm, os=WIN)
