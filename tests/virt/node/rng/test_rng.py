"""
Test VM with RNG
"""

import shlex

import pytest
from pyhelper_utils.shell import run_ssh_commands

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


@pytest.fixture()
def rng_vm(unprivileged_client, namespace):
    name = "vmi-with-rng"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.polarion("CNV-791")
def test_vm_with_rng(rng_vm):
    """
    Test VM with RNG
     - check random device should be present
     - create random data with each device
    """
    rng_current_cmd = ["cat", "/sys/devices/virtual/misc/hw_random/rng_current"]

    rng_commnds = [
        shlex.split(f"sudo dd count=10 bs=1024 if=/dev/{device} of=/tmp/{device}.txt && ls /tmp/{device}.txt | wc -l")
        for device in ["random", "hwrng"]
    ] + [rng_current_cmd]
    rng_output = run_ssh_commands(
        host=rng_vm.ssh_exec,
        commands=rng_commnds,
    )
    assert set(rng_output[:2]) == {"1\n"}, f"Expected:1, actual: {rng_output[:2]}"
    assert rng_output[-1].strip() == "virtio_rng.0", f"rng_current: {rng_output[0]}"
