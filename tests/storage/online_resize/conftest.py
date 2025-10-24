# -*- coding: utf-8 -*-

"""
Fixtures for online resize tests
"""

import pytest

from tests.storage.online_resize.utils import (
    SMALLEST_POSSIBLE_EXPAND,
    STORED_FILENAME,
    cksum_file,
    clone_dv,
    expand_pvc,
    wait_for_resize,
)
from tests.storage.utils import create_rhel_dv
from utilities.constants import OS_FLAVOR_RHEL, Images
from utilities.storage import is_snapshot_supported_by_sc
from utilities.virt import VirtualMachineForTests, running_vm


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


@pytest.fixture()
def orig_cksum(rhel_vm_for_online_resize, running_rhel_vm):
    return cksum_file(vm=rhel_vm_for_online_resize, filename=STORED_FILENAME, create=True)


@pytest.fixture()
def rhel_dv_for_online_resize(
    request,
    namespace,
    storage_class_matrix_online_resize_matrix__module__,
    rhel_data_source_scope_module,
):
    with create_rhel_dv(
        namespace=namespace.name,
        name=request.param["vm_name"],
        storage_class=[*storage_class_matrix_online_resize_matrix__module__][0],
        rhel_data_source_scope_module=rhel_data_source_scope_module,
    ) as dv:
        yield dv


@pytest.fixture()
def second_rhel_dv_for_online_resize(rhel_dv_for_online_resize):
    with clone_dv(
        dv=rhel_dv_for_online_resize,
        size=rhel_dv_for_online_resize.size,
    ) as rhel_dv:
        yield rhel_dv


@pytest.fixture()
def rhel_vm_for_online_resize(request, unprivileged_client, namespace, rhel_dv_for_online_resize):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=request.param["vm_name"],
        namespace=namespace.name,
        data_volume=rhel_dv_for_online_resize,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        os_flavor=OS_FLAVOR_RHEL,
    ) as vm:
        yield vm


@pytest.fixture()
def rhel_vm_after_expand(rhel_dv_for_online_resize, rhel_vm_for_online_resize, running_rhel_vm):
    with wait_for_resize(vm=rhel_vm_for_online_resize):
        expand_pvc(dv=rhel_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)
    return rhel_vm_for_online_resize


@pytest.fixture()
def running_rhel_vm(rhel_vm_for_online_resize):
    running_vm(vm=rhel_vm_for_online_resize)
