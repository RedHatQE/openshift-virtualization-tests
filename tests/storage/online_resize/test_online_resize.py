# -*- coding: utf-8 -*-

"""
Online resize (PVC expanded while VM running)
"""

import logging

import pytest
from ocp_resources.datavolume import DataVolume
from timeout_sampler import TimeoutSampler

from tests.storage.online_resize.utils import (
    RHEL_DV_SIZE,
    SMALLEST_POSSIBLE_EXPAND,
    check_file_unchanged,
    expand_pvc,
    vm_restore,
    wait_for_resize,
)
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_4MIN, TIMEOUT_5SEC
from utilities.storage import add_dv_to_vm, create_dv, vm_snapshot
from utilities.virt import migrate_vm_and_verify, running_vm

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.usefixtures("xfail_if_gcp_storage_class")


@pytest.mark.gating
@pytest.mark.conformance
@pytest.mark.polarion("CNV-6793")
@pytest.mark.parametrize(
    "rhel_dv_for_online_resize, rhel_vm_for_online_resize",
    [
        pytest.param(
            {"dv_name": "sequential-expand-dv"},
            {"vm_name": "sequential-expand-vm"},
        ),
    ],
    indirect=True,
)
def test_sequential_disk_expand(
    rhel_dv_for_online_resize,
    rhel_vm_for_online_resize,
    running_rhel_vm,
):
    # Expand PVC and wait for resize 6 times
    for _ in range(6):
        with wait_for_resize(vm=rhel_vm_for_online_resize):
            expand_pvc(dv=rhel_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)


@pytest.mark.polarion("CNV-6794")
@pytest.mark.parametrize(
    "rhel_dv_for_online_resize, rhel_vm_for_online_resize",
    [
        pytest.param(
            {"dv_name": "simultaneous-expand-dv"},
            {"vm_name": "simultaneous-expand-vm"},
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_simultaneous_disk_expand(
    rhel_dv_for_online_resize,
    second_rhel_dv_for_online_resize,
    rhel_vm_for_online_resize,
):
    add_dv_to_vm(vm=rhel_vm_for_online_resize, dv_name=second_rhel_dv_for_online_resize.name)
    running_vm(vm=rhel_vm_for_online_resize)
    with wait_for_resize(vm=rhel_vm_for_online_resize, count=2):
        expand_pvc(dv=rhel_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)
        expand_pvc(dv=second_rhel_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)


@pytest.mark.polarion("CNV-8257")
@pytest.mark.parametrize(
    "rhel_dv_for_online_resize, rhel_vm_for_online_resize",
    [
        pytest.param(
            {"dv_name": "expand-clone-fail-dv"},
            {"vm_name": "expand-clone-fail-vm"},
        ),
    ],
    indirect=True,
)
def test_disk_expand_then_clone_fail(
    unprivileged_client,
    rhel_dv_for_online_resize,
    rhel_vm_after_expand,
):
    LOGGER.info("Trying to clone DV with original size - should fail at webhook")
    with create_dv(
        source="pvc",
        dv_name=f"{rhel_dv_for_online_resize.name}-target",
        namespace=rhel_dv_for_online_resize.namespace,
        client=unprivileged_client,
        size=RHEL_DV_SIZE,
        storage_class=rhel_dv_for_online_resize.storage_class,
        source_pvc=rhel_dv_for_online_resize.name,
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
@pytest.mark.conformance
@pytest.mark.polarion("CNV-6578")
@pytest.mark.parametrize(
    "rhel_dv_for_online_resize, rhel_vm_for_online_resize",
    [
        pytest.param(
            {"dv_name": "expand-clone-success-dv"},
            {"vm_name": "expand-clone-success-vm"},
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_disk_expand_then_clone_success(
    unprivileged_client,
    rhel_dv_for_online_resize,
    rhel_vm_after_expand,
):
    # Can't clone a running VM
    rhel_vm_after_expand.stop()

    LOGGER.info("Trying to clone DV with new size - should succeed")
    with create_dv(
        source="pvc",
        dv_name=f"{rhel_dv_for_online_resize.name}-target",
        namespace=rhel_dv_for_online_resize.namespace,
        client=unprivileged_client,
        size=rhel_dv_for_online_resize.pvc.instance.spec.resources.requests.storage,
        storage_class=rhel_dv_for_online_resize.storage_class,
        source_pvc=rhel_dv_for_online_resize.name,
    ) as cdv:
        cdv.wait_for_condition(
            condition=DataVolume.Condition.Type.READY,
            status=DataVolume.Condition.Status.TRUE,
            timeout=TIMEOUT_4MIN,
        )


@pytest.mark.polarion("CNV-6580")
@pytest.mark.parametrize(
    "rhel_dv_for_online_resize, rhel_vm_for_online_resize",
    [
        pytest.param(
            {"dv_name": "expand-migrate-dv"},
            {"vm_name": "expand-migrate-vm"},
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_disk_expand_then_migrate(rhel_vm_after_expand, orig_cksum):
    migrate_vm_and_verify(
        vm=rhel_vm_after_expand,
        check_ssh_connectivity=True,
    )
    check_file_unchanged(orig_cksum=orig_cksum, vm=rhel_vm_after_expand)


@pytest.mark.polarion("CNV-6797")
@pytest.mark.parametrize(
    "rhel_dv_for_online_resize, rhel_vm_for_online_resize",
    [
        pytest.param(
            {"dv_name": "expand-snapshot-dv"},
            {"vm_name": "expand-snapshot-vm"},
        ),
    ],
    indirect=True,
)
def test_disk_expand_with_snapshots(
    xfail_if_storage_for_online_resize_does_not_support_snapshots,
    rhel_dv_for_online_resize,
    rhel_vm_for_online_resize,
    orig_cksum,
):
    with vm_snapshot(vm=rhel_vm_for_online_resize, name="snapshot-before") as vm_snapshot_before:
        with wait_for_resize(vm=rhel_vm_for_online_resize):
            expand_pvc(dv=rhel_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)
        check_file_unchanged(orig_cksum=orig_cksum, vm=rhel_vm_for_online_resize)
        with vm_snapshot(vm=rhel_vm_for_online_resize, name="snapshot-after") as vm_snapshot_after:
            with vm_restore(vm=rhel_vm_for_online_resize, name=vm_snapshot_before.name) as vm_restored_before:
                check_file_unchanged(orig_cksum=orig_cksum, vm=vm_restored_before)
            with vm_restore(vm=rhel_vm_for_online_resize, name=vm_snapshot_after.name) as vm_restored_after:
                check_file_unchanged(orig_cksum=orig_cksum, vm=vm_restored_after)
