"""
Pytest conftest for snapshot/restore across RHCOS versions
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest

from tests.storage.rhel9_rhel10_cluster.constants import SNAPSHOT_TEST_DATA, SNAPSHOT_TEST_FILE
from utilities.storage import data_volume_template_with_source_ref_dict, write_file_via_ssh
from utilities.virt import VirtualMachineForTests, running_vm

if TYPE_CHECKING:
    from ocp_resources.data_source import DataSource
    from ocp_resources.namespace import Namespace


@pytest.fixture()
def dual_stream_snapshot_vm(
    request: pytest.FixtureRequest,
    unprivileged_client,
    namespace: Namespace,
    rhel10_data_source_scope_session: DataSource,
    storage_class_matrix_snapshot_matrix__function__: dict,
) -> Generator[VirtualMachineForTests]:
    """Create RHEL VM on a specified RHCOS node, write test data, and stop it.

    VM is created with affinity to source RHCOS version, brought up, test data
    written to disk, then stopped in preparation for snapshot/restore testing.

    Yields:
        VirtualMachineForTests: Stopped VM with test data on disk, ready for snapshot.
    """
    with VirtualMachineForTests(
        name=request.param["vm_name"],
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel10_data_source_scope_session,
            storage_class=next(iter(storage_class_matrix_snapshot_matrix__function__)),
        ),
        vm_affinity=request.param["vm_affinity"],
    ) as vm:
        running_vm(vm=vm)
        write_file_via_ssh(vm=vm, filename=SNAPSHOT_TEST_FILE, content=SNAPSHOT_TEST_DATA)
        vm.stop(wait=True)
        yield vm
