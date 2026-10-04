import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine_instance_migration import VirtualMachineInstanceMigration

from utilities.constants.timeouts import TIMEOUT_3MIN
from utilities.constants.virt import MIGRATION_POLICY_VM_LABEL
from utilities.virt import (
    get_data_volume_template_dict_with_default_storage_class,
    get_or_create_golden_image_data_source,
    vm_instance_from_template,
)


@pytest.fixture(scope="class")
def dual_stream_migration_metrics_policy(request, admin_client):
    """Create a MigrationPolicy with bandwidth throttling to sample metrics during migration.

    Bandwidth is intentionally limited to allow Prometheus metrics to be collected while migration
    is in progress. Completion timeout is set high (10000s per GB) to accommodate the slow transfer.

    Yields:
        MigrationPolicy: The created migration policy; deleted on teardown.
    """
    with MigrationPolicy(
        client=admin_client,
        name="dual-stream-migration-metrics-policy",
        bandwidth_per_migration=request.param["bandwidth"],
        completion_timeout_per_gb=10000,
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as policy:
        yield policy


@pytest.fixture(scope="module")
def golden_image_data_source_for_dual_stream_scope_module(request, admin_client, golden_images_namespace):
    yield from get_or_create_golden_image_data_source(
        admin_client=admin_client, golden_images_namespace=golden_images_namespace, os_dict=request.param["os_dict"]
    )


@pytest.fixture(scope="module")
def golden_image_data_volume_template_for_dual_stream_scope_module(
    golden_image_data_source_for_dual_stream_scope_module,
):
    return get_data_volume_template_dict_with_default_storage_class(
        data_source=golden_image_data_source_for_dual_stream_scope_module
    )


@pytest.fixture(scope="class")
def dual_stream_golden_image_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_dual_stream_scope_module,
    modern_cpu_for_migration,
):
    """Create and start a VM from a golden image template with specified affinity.

    Yields:
        VirtualMachineForTests: The running VM; deleted on teardown.
    """
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_dual_stream_scope_module,
        vm_cpu_model=modern_cpu_for_migration,
        vm_affinity=request.param.get("vm_affinity"),
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def dual_stream_migration_metrics_vmim(
    admin_client,
    dual_stream_golden_image_vm,
    updated_vm_affinity,
):
    with VirtualMachineInstanceMigration(
        name=dual_stream_golden_image_vm.name,
        namespace=dual_stream_golden_image_vm.namespace,
        vmi_name=dual_stream_golden_image_vm.vmi.name,
        client=admin_client,
    ) as vmim:
        vmim.wait_for_status(status=vmim.Status.RUNNING, timeout=TIMEOUT_3MIN)
        yield vmim


@pytest.fixture(scope="class")
def updated_vm_affinity(request, dual_stream_golden_image_vm):
    with ResourceEditor(
        patches={
            dual_stream_golden_image_vm: {
                "spec": {"template": {"spec": {"affinity": request.param["target_affinity"]}}}
            }
        }
    ):
        yield
