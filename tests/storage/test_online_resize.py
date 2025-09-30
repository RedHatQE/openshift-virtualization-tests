# -*- coding: utf-8 -*-

"""
Online resize (PVC expanded while VM running)
"""

import logging
import shlex
from contextlib import contextmanager

import bitmath
import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.storage.utils import create_cirros_dv
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_4MIN, TIMEOUT_5SEC, Images
from utilities.storage import (
    add_dv_to_vm,
    create_dv,
    is_snapshot_supported_by_sc,
    vm_snapshot,
)
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify, running_vm

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
    commands = shlex.split("dmesg | grep -c 'new size' || true")
    return int(run_ssh_commands(host=vm.ssh_exec, commands=commands)[0])


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


@pytest.fixture()
def cirros_dv_for_online_resize(
    namespace,
    cirros_vm_name,
    storage_class_matrix_online_resize_matrix__module__,
):
    yield from create_cirros_dv(
        namespace=namespace.name,
        name=cirros_vm_name,
        storage_class=[*storage_class_matrix_online_resize_matrix__module__][0],
    )


@pytest.fixture()
def second_cirros_dv_for_online_resize(cirros_dv_for_online_resize):
    with clone_dv(
        dv=cirros_dv_for_online_resize,
        size=cirros_dv_for_online_resize.size,
    ) as second_dv:
        yield second_dv


@pytest.fixture()
def cirros_vm_for_online_resize(
    admin_client,
    cirros_dv_for_online_resize,
    namespace,
    cirros_vm_name,
):
    """
    Create a VM with a DV from the cirros_dv_for_online_resize fixture
    """
    with VirtualMachineForTests(
        name=cirros_vm_name,
        namespace=namespace.name,
        data_volume=cirros_dv_for_online_resize,
        memory_guest=Images.Cirros.DEFAULT_MEMORY_SIZE,
        os_flavor=Images.Cirros.OS_FLAVOR,
    ) as vm:
        yield vm


@pytest.fixture()
def cirros_vm_after_expand(cirros_dv_for_online_resize, cirros_vm_for_online_resize, running_cirros_vm):
    with wait_for_resize(vm=cirros_vm_for_online_resize):
        expand_pvc(dv=cirros_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)
    return cirros_vm_for_online_resize


@pytest.fixture()
def running_cirros_vm(cirros_vm_for_online_resize):
    running_vm(vm=cirros_vm_for_online_resize, wait_for_interfaces=False)


@pytest.fixture()
def orig_cksum(cirros_vm_for_online_resize, running_cirros_vm):
    return cksum_file(vm=cirros_vm_for_online_resize, filename=STORED_FILENAME, create=True)


@pytest.fixture(scope="module")
def skip_if_storage_for_online_resize_does_not_support_snapshots(
    storage_class_matrix_online_resize_matrix__module__, admin_client
):
    sc_name = [*storage_class_matrix_online_resize_matrix__module__][0]
    if not is_snapshot_supported_by_sc(
        sc_name=sc_name,
        client=admin_client,
    ):
        pytest.skip(f"Storage class for online resize '{sc_name}' doesn't support snapshots")


@pytest.mark.gating
@pytest.mark.polarion("CNV-6793")
@pytest.mark.parametrize(
    "cirros_vm_name",
    [
        pytest.param(
            {"vm_name": "cnv-6793"},
        ),
    ],
    indirect=True,
)
def test_sequential_disk_expand(
    cirros_dv_for_online_resize,
    cirros_vm_for_online_resize,
    running_cirros_vm,
):
    # Expand PVC and wait for resize 6 times
    for _ in range(6):
        with wait_for_resize(vm=cirros_vm_for_online_resize):
            expand_pvc(dv=cirros_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)


@pytest.mark.polarion("CNV-6794")
@pytest.mark.parametrize(
    "cirros_vm_name",
    [
        pytest.param(
            {"vm_name": "cnv-6794"},
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_simultaneous_disk_expand(
    cirros_dv_for_online_resize,
    second_cirros_dv_for_online_resize,
    cirros_vm_for_online_resize,
):
    add_dv_to_vm(vm=cirros_vm_for_online_resize, dv_name=second_cirros_dv_for_online_resize.name)
    running_vm(vm=cirros_vm_for_online_resize, wait_for_interfaces=False)
    with wait_for_resize(vm=cirros_vm_for_online_resize, count=2):
        expand_pvc(dv=cirros_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)
        expand_pvc(dv=second_cirros_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)


@pytest.mark.polarion("CNV-8257")
@pytest.mark.parametrize(
    "cirros_vm_name",
    [
        pytest.param(
            {"vm_name": "cnv-8257"},
        ),
    ],
    indirect=True,
)
def test_disk_expand_then_clone_fail(
    cirros_dv_for_online_resize,
    cirros_vm_after_expand,
):
    LOGGER.info("Trying to clone DV with original size - should fail at webhook")
    with clone_dv(
        dv=cirros_dv_for_online_resize,
        size=Images.Cirros.DEFAULT_DV_SIZE,
    ) as dv:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: dv.instance.status.conditions,
        ):
            if any(
                "The clone doesn't meet the validation requirements:"
                " target resources requests storage size is smaller than the source" in condition["message"]
                for condition in sample
            ):
                return


@pytest.mark.gating
@pytest.mark.polarion("CNV-6578")
@pytest.mark.parametrize(
    "cirros_vm_name",
    [
        pytest.param(
            {"vm_name": "cnv-6578"},
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_disk_expand_then_clone_success(
    cirros_dv_for_online_resize,
    cirros_vm_after_expand,
):
    # Can't clone a running VM
    cirros_vm_after_expand.stop()

    LOGGER.info("Trying to clone DV with new size - should succeed")
    with clone_dv(
        dv=cirros_dv_for_online_resize,
        size=cirros_dv_for_online_resize.pvc.instance.spec.resources.requests.storage,
    ) as cdv:
        cdv.wait_for_condition(
            condition=DataVolume.Condition.Type.READY,
            status=DataVolume.Condition.Status.TRUE,
            timeout=TIMEOUT_4MIN,
        )


@pytest.mark.polarion("CNV-6580")
@pytest.mark.parametrize(
    "cirros_vm_name",
    [
        pytest.param(
            {"vm_name": "cnv-6580"},
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_disk_expand_then_migrate(cpu_for_migration, cirros_vm_after_expand, orig_cksum):
    migrate_vm_and_verify(
        vm=cirros_vm_after_expand,
        wait_for_interfaces=False,
        check_ssh_connectivity=True,
    )
    check_file_unchanged(orig_cksum=orig_cksum, vm=cirros_vm_after_expand)


@pytest.mark.polarion("CNV-6797")
@pytest.mark.parametrize(
    "cirros_vm_name",
    [
        pytest.param(
            {"vm_name": "cnv-6797"},
        ),
    ],
    indirect=True,
)
def test_disk_expand_with_snapshots(
    skip_if_storage_for_online_resize_does_not_support_snapshots,
    cirros_dv_for_online_resize,
    cirros_vm_for_online_resize,
    orig_cksum,
):
    with vm_snapshot(vm=cirros_vm_for_online_resize, name="snapshot-before") as vm_snapshot_before:
        with wait_for_resize(vm=cirros_vm_for_online_resize):
            expand_pvc(dv=cirros_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)
        check_file_unchanged(orig_cksum=orig_cksum, vm=cirros_vm_for_online_resize)
        with vm_snapshot(vm=cirros_vm_for_online_resize, name="snapshot-after") as vm_snapshot_after:
            with vm_restore(vm=cirros_vm_for_online_resize, name=vm_snapshot_before.name) as vm_restored_before:
                check_file_unchanged(orig_cksum=orig_cksum, vm=vm_restored_before)
            with vm_restore(vm=cirros_vm_for_online_resize, name=vm_snapshot_after.name) as vm_restored_after:
                check_file_unchanged(orig_cksum=orig_cksum, vm=vm_restored_after)
