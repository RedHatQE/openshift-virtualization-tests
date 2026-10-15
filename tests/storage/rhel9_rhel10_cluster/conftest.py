"""
Pytest conftest for snapshot/restore across RHCOS versions
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest

from tests.storage.rhel9_rhel10_cluster.constants import (
    SNAPSHOT_TEST_DATA,
    SNAPSHOT_TEST_FILE,
)
from tests.storage.rhel9_rhel10_cluster.snapshot_utils import assert_vm_rhcos_version
from utilities.storage import data_volume_template_with_source_ref_dict, write_file_via_ssh
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    get_or_create_golden_image_data_source,
    running_vm,
    vm_instance_from_template,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.namespace import Namespace


@pytest.fixture()
def golden_image_data_source_for_dual_stream_scope_function(
    request: pytest.FixtureRequest,
    admin_client: DynamicClient,
    golden_images_namespace: Namespace,
):
    """Create golden image DataSource from parametrize os_dict.

    Yields:
        DataSource: Golden image DataSource for the specified OS.
    """
    yield from get_or_create_golden_image_data_source(
        admin_client=admin_client,
        golden_images_namespace=golden_images_namespace,
        os_dict=request.param["os_dict"],
    )


@pytest.fixture()
def dual_stream_snapshot_vm(
    request: pytest.FixtureRequest,
    admin_client: DynamicClient,
    unprivileged_client: DynamicClient,
    namespace: Namespace,
    golden_image_data_source_for_dual_stream_scope_function,
    storage_class_for_snapshot,
) -> Generator[VirtualMachineForTestsFromTemplate]:
    """Create VM for dual-stream snapshot/restore testing.

    Sets up VM in known state: started with test data, then stopped on source RHCOS.
    Verifies VM is on expected source RHCOS before yielding.

    Yields:
        VirtualMachineForTestsFromTemplate: VM in stopped state with test data on disk.
    """
    data_volume_template = data_volume_template_with_source_ref_dict(
        data_source=golden_image_data_source_for_dual_stream_scope_function,
        storage_class=storage_class_for_snapshot,
    )
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=data_volume_template,
        vm_affinity=request.param.get("vm_affinity"),
    ) as vm:
        # Set up VM in known state for snapshot testing
        running_vm(vm=vm)
        assert_vm_rhcos_version(
            vm=vm,
            admin_client=admin_client,
            expected_os=request.param["source_rhcos_version"],
        )
        write_file_via_ssh(vm=vm, filename=SNAPSHOT_TEST_FILE, content=SNAPSHOT_TEST_DATA)
        vm.stop(wait=True)
        yield vm
