import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.virtual_machine_instance_migration import VirtualMachineInstanceMigration

from utilities.constants.timeouts import TIMEOUT_3MIN
from utilities.constants.virt import MIGRATION_POLICY_VM_LABEL, MIGRATION_POLICY_WINDOWS_VM_LABEL
from utilities.virt import (
    get_data_volume_template_dict_with_default_storage_class,
    get_or_create_golden_image_data_source,
    set_vm_affinity,
    vm_instance_from_template,
)


@pytest.fixture(scope="module")
def dual_stream_migration_metrics_policy(admin_client):
    with MigrationPolicy(
        client=admin_client,
        name="dual-stream-migration-metrics-policy",
        bandwidth_per_migration="128Ki",
        completion_timeout_per_gb=10000,
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as policy:
        yield policy


@pytest.fixture(scope="module")
def dual_stream_migration_metrics_windows_policy(admin_client):
    # A plain (unthrottled) migration completes too quickly for metrics to be sampled mid-flight.
    # The Windows template's guest memory is 8Gi, much larger than the RHEL VM's, so it needs a much
    # higher bandwidth cap than the RHEL policy to converge in a reasonable time (~4 minutes at 32Mi/s,
    # vs. hours at 256Ki/s).
    with MigrationPolicy(
        client=admin_client,
        name="dual-stream-migration-metrics-windows-policy",
        bandwidth_per_migration="32Mi",
        completion_timeout_per_gb=10000,
        vmi_selector=MIGRATION_POLICY_WINDOWS_VM_LABEL,
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


@pytest.fixture(scope="module")
def dual_stream_golden_image_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_dual_stream_scope_module,
    modern_cpu_for_migration,
):
    # Shared by all migration-metrics/start-time/end-time tests for a given (OS, direction), so an
    # expensive VM (especially Windows) is created and migrated only once instead of per test.
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
    request,
    admin_client,
    dual_stream_golden_image_vm,
):
    set_vm_affinity(vm=dual_stream_golden_image_vm, affinity=request.param["target_affinity"])
    with VirtualMachineInstanceMigration(
        name=dual_stream_golden_image_vm.name,
        namespace=dual_stream_golden_image_vm.namespace,
        vmi_name=dual_stream_golden_image_vm.vmi.name,
        client=admin_client,
    ) as vmim:
        vmim.wait_for_status(status=vmim.Status.RUNNING, timeout=TIMEOUT_3MIN)
        yield vmim
