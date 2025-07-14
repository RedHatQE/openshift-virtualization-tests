"""
Test VM with memory requests/limits and guest memory for OOM.
"""

import logging
import shlex
from contextlib import contextmanager
from threading import Event, Thread

import pytest
from ocp_resources.virtual_machine import VirtualMachine
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.os_params import WINDOWS_10_TEMPLATE_LABELS
from tests.virt.constants import STRESS_CPU_MEM_IO_COMMAND
from tests.virt.utils import get_virt_launcher_processes_memory_overuse, start_stress_on_vm
from utilities.constants import TCP_TIMEOUT_30SEC, TIMEOUT_15MIN, Images
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

pytestmark = pytest.mark.tier3

LOGGER = logging.getLogger(__name__)


STRESS_OOM_COMMAND = STRESS_CPU_MEM_IO_COMMAND.format(workers="1", memory="100%", timeout="30m")


def verify_vm_not_crashed(vm):
    with start_file_transfer(vm=vm):
        assert wait_vm_oom(vm=vm), "VM crashed"


def verify_memory_overuse(pod):
    memory_overuse = get_virt_launcher_processes_memory_overuse(pod=pod)
    assert not memory_overuse, f"Memory overuse: \n{memory_overuse}"


@pytest.fixture()
def fedora_oom_vm(namespace, unprivileged_client):
    name = "oom-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        cpu_cores=2,
        cpu_requests="2",
        cpu_limits="2",
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def fedora_oom_stress_started(fedora_oom_vm):
    start_stress_on_vm(vm=fedora_oom_vm, stress_command=STRESS_OOM_COMMAND)


@pytest.fixture()
def windows_oom_stress_started(vm_with_memory_load):
    start_stress_on_vm(vm=vm_with_memory_load, stress_command=STRESS_OOM_COMMAND)


@contextmanager
def start_file_transfer(vm):
    file_name = "oom-test.txt"

    def _transfer_loop(stop_event):
        while not stop_event.is_set():
            vm.ssh_exec.fs.transfer(path_src=file_name, target_host=vm.ssh_exec, path_dst="new_file")

    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(f"{'wsl' if 'windows' in vm.name else ''} dd if=/dev/zero of={file_name} bs=100M count=1"),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )

    stop_event = Event()
    transfer = Thread(target=_transfer_loop, args=(stop_event,), daemon=True)

    transfer.start()

    try:
        yield
    finally:
        stop_event.set()


def wait_vm_oom(vm):
    LOGGER.info(f"Monitoring VM {vm.name} under stress for 15 min")
    virt_launcher_pod = vm.vmi.virt_launcher_pod
    samples = TimeoutSampler(wait_timeout=TIMEOUT_15MIN, sleep=10, func=lambda: virt_launcher_pod.status)
    try:
        for sample in samples:
            if sample != virt_launcher_pod.Status.RUNNING:
                return
    except TimeoutExpiredError:
        return True


@pytest.mark.polarion("CNV-5321")
def test_vm_fedora_oom(fedora_oom_vm, fedora_oom_stress_started):
    verify_vm_not_crashed(vm=fedora_oom_vm)
    verify_memory_overuse(pod=fedora_oom_vm.privileged_vmi.virt_launcher_pod)


@pytest.mark.ibm_bare_metal
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, vm_with_memory_load",
    [
        pytest.param(
            {
                "dv_name": "dv-win10-wsl2",
                "image": f"{Images.Windows.UEFI_WIN_DIR}/{Images.Windows.WIN10_WSL2_IMG}",
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "windows-vm-with-memory-load",
                "template_labels": WINDOWS_10_TEMPLATE_LABELS,
                "memory_guest": Images.Windows.DEFAULT_MEMORY_SIZE_WSL,
                "cpu_cores": 16,
                "cpu_threads": 1,
            },
            marks=pytest.mark.polarion("CNV-9893"),
        ),
    ],
    indirect=True,
)
@pytest.mark.special_infra
@pytest.mark.high_resource_vm
def test_vm_windows_oom(vm_with_memory_load, windows_oom_stress_started):
    verify_vm_not_crashed(vm=vm_with_memory_load)
    verify_memory_overuse(pod=vm_with_memory_load.privileged_vmi.virt_launcher_pod)
