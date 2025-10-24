# -*- coding: utf-8 -*-

"""
Utility functions and context managers for online resize tests
"""

import logging
import shlex
from contextlib import contextmanager

import bitmath
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_4MIN
from utilities.storage import create_dv
from utilities.virt import running_vm

LOGGER = logging.getLogger(__name__)
SMALLEST_POSSIBLE_EXPAND = "1Gi"
STORED_FILENAME = "random_data_file"


@contextmanager
def clone_dv(dv, size):
    with create_dv(
        source="pvc",
        dv_name=f"{dv.name}-target",
        namespace=dv.namespace,
        size=size,
        storage_class=dv.storage_class,
        volume_mode=dv.volume_mode,
        source_pvc=dv.name,
    ) as dv:
        yield dv


def cksum_file(vm, filename, create=False):
    """

    Return the checksum of a previously generated file.
    If requested, create the file using random data.

    Args:
        vm (VirtualMachine): vm to run commands on
        filename (str): The filename which we checksum
        create (bool): Whether to create the file first

    Returns:
        str: the SHA256 checksum of the file

    """
    if create:
        LOGGER.info("Creating file with random data")
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(f"dd if=/dev/urandom of={filename} count=100 && sync"),
        )

    out = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split(f"sha256sum {filename}"))[0]
    sha256sum = out.split()[0]
    LOGGER.info(f"File sha256sum is {sha256sum}")
    return sha256sum


def kubsize_add(a_size, b_size):
    """

    Sum two kubernetes size strings.
    Output sum is provided in a format that is accepted by kubernetes
    as a storage size.

    Args:
        a_size (str): size string to be summed
        b_size (str): second size string

    Returns:
        str: a sum of the inputs tolerated by kubernetes

    """
    bm_a = bitmath.parse_string_unsafe(s=a_size)
    bm_b = bitmath.parse_string_unsafe(s=b_size)

    bm_sum = bm_a + bm_b
    return f"{bm_sum.bytes:0.0f}"


def expand_pvc(dv, size_change):
    pvc = dv.pvc
    new_size = kubsize_add(a_size=pvc.instance.spec.resources.requests.storage, b_size=size_change)
    pvc.update({
        "metadata": {"name": dv.name},
        "spec": {
            "resources": {"requests": {"storage": new_size}},
        },
    })


def get_resize_count(vm):
    commands = shlex.split("sudo dmesg | grep -c 'new size' || true")
    result = run_ssh_commands(host=vm.ssh_exec, commands=commands)[0]

    return int(result)


def check_file_unchanged(orig_cksum, vm):
    new_cksum = cksum_file(vm=vm, filename=STORED_FILENAME)
    assert orig_cksum == new_cksum, (
        f"File checksum changed, original checksum={orig_cksum}, current checksum={new_cksum}"
    )


@contextmanager
def wait_for_resize(vm, count=1):
    starting_count = get_resize_count(vm=vm)
    desired_count = starting_count + count
    yield
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_4MIN,
        sleep=5,
        func=get_resize_count,
        vm=vm,
    )
    try:
        for sample in samples:
            current_resize_count = sample
            LOGGER.info(
                f"Current resize count is {current_resize_count}. Waiting until resize count is {desired_count}"
            )
            if current_resize_count in (desired_count, desired_count + 1):
                break
    except TimeoutExpiredError:
        dmesg = run_ssh_commands(host=vm.ssh_exec, commands=shlex.split("dmesg"))[0]
        LOGGER.error(f"Failed to reach resize count {desired_count}.\ndmesg:\n{dmesg}")
        raise


@contextmanager
def vm_restore(vm, name):
    vm.stop(wait=True)
    with VirtualMachineRestore(
        name=f"restore-{name}",
        namespace=vm.namespace,
        vm_name=vm.name,
        snapshot_name=name,
    ) as restore:
        restore.wait_restore_done()
        running_vm(vm=vm, wait_for_interfaces=False)
        yield vm
