# -*- coding: utf-8 -*-

"""
Fixtures for online resize tests
"""

import pytest

from tests.storage.online_resize.constants import (
    SMALLEST_POSSIBLE_EXPAND,
    STORED_FILENAME,
)
from tests.storage.online_resize.utils import (
    cksum_file,
    create_rhel_dv_from_data_source,
    expand_pvc,
    wait_for_resize,
)
from utilities.constants import OS_FLAVOR_RHEL, Images, StorageClassNames
from utilities.storage import add_dv_to_vm, create_dv
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify, running_vm


@pytest.fixture(scope="module")
def xfail_if_storage_for_online_resize_does_not_support_snapshots(
    storage_class_matrix_online_resize_matrix__module__,
):
    sc_name = [*storage_class_matrix_online_resize_matrix__module__][0]
    if storage_class_matrix_online_resize_matrix__module__[sc_name].get("snapshot") is not True:
        pytest.xfail(f"Storage class for online resize '{sc_name}' doesn't support snapshots")


@pytest.fixture(scope="module")
def xfail_if_gcp_storage_class(storage_class_matrix_online_resize_matrix__module__):
    sc_name = next(iter(storage_class_matrix_online_resize_matrix__module__))
    if sc_name == StorageClassNames.GCP:
        pytest.xfail("Online resize is not supported for GCP storage class for RWX Datavolume")


@pytest.fixture()
def orig_cksum(rhel_vm_for_online_resize, running_rhel_vm):
    return cksum_file(vm=rhel_vm_for_online_resize, filename=STORED_FILENAME, create=True)


@pytest.fixture()
def rhel_dv_for_online_resize(
    request,
    namespace,
    unprivileged_client,
    storage_class_matrix_online_resize_matrix__module__,
    rhel10_data_source_scope_module,
):
    with create_rhel_dv_from_data_source(
        unprivileged_client=unprivileged_client,
        namespace=namespace.name,
        name=request.param["dv_name"],
        storage_class=[*storage_class_matrix_online_resize_matrix__module__][0],
        rhel_data_source=rhel10_data_source_scope_module,
    ) as dv:
        yield dv


@pytest.fixture()
def second_rhel_dv_for_online_resize(rhel_dv_for_online_resize, unprivileged_client):
    with create_dv(
        source="pvc",
        dv_name=f"{rhel_dv_for_online_resize.name}-target",
        namespace=rhel_dv_for_online_resize.namespace,
        client=unprivileged_client,
        size=rhel_dv_for_online_resize.size,
        storage_class=rhel_dv_for_online_resize.storage_class,
        source_pvc=rhel_dv_for_online_resize.name,
    ) as rhel_dv:
        yield rhel_dv


@pytest.fixture()
def rhel_vm_for_online_resize(
    request, unprivileged_client, namespace, rhel_dv_for_online_resize, modern_cpu_for_migration
):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=request.param["vm_name"],
        namespace=namespace.name,
        data_volume=rhel_dv_for_online_resize,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        os_flavor=OS_FLAVOR_RHEL,
        cpu_model=modern_cpu_for_migration,
    ) as vm:
        yield vm


@pytest.fixture()
def rhel_vm_after_expand(rhel_dv_for_online_resize, rhel_vm_for_online_resize, running_rhel_vm):
    with wait_for_resize(vm=rhel_vm_for_online_resize):
        expand_pvc(dv=rhel_dv_for_online_resize, size_change=SMALLEST_POSSIBLE_EXPAND)
    return rhel_vm_for_online_resize


@pytest.fixture()
def running_rhel_vm(rhel_vm_for_online_resize):
    return running_vm(vm=rhel_vm_for_online_resize)


@pytest.fixture()
def running_rhel_vm_with_second_dv(rhel_vm_for_online_resize, second_rhel_dv_for_online_resize):
    add_dv_to_vm(vm=rhel_vm_for_online_resize, dv_name=second_rhel_dv_for_online_resize.name)
    running_vm(vm=rhel_vm_for_online_resize)
    return rhel_vm_for_online_resize


@pytest.fixture()
def rhel_vm_after_expand_and_migrate(rhel_vm_after_expand):
    migrate_vm_and_verify(vm=rhel_vm_after_expand, check_ssh_connectivity=True)
    return rhel_vm_after_expand
