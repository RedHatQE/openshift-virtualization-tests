import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.virtual_machine_instance_migration import VirtualMachineInstanceMigration

from utilities.constants.timeouts import TIMEOUT_3MIN
from utilities.constants.virt import MIGRATION_POLICY_VM_LABEL
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    get_data_volume_template_dict_with_default_storage_class,
    get_or_create_golden_image_data_source,
    migrate_vm_and_verify,
    running_vm,
    set_vm_affinity,
    vm_instance_from_template,
)


@pytest.fixture(scope="class")
def dual_stream_migration_metrics_policy(admin_client):
    # Bandwidth is capped low so metrics are sampled while migration is in progress. The cluster's
    # default completionTimeoutPerGiB is far too tight for that throttled rate (it would abort the
    # migration before it can converge), so it's overridden here to fit the 128Ki bandwidth cap.
    with MigrationPolicy(
        client=admin_client,
        name="dual-stream-migration-metrics-policy",
        bandwidth_per_migration="128Ki",
        completion_timeout_per_gb=10000,
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as policy:
        yield policy


@pytest.fixture(scope="class")
def dual_stream_migration_metrics_vm(request, namespace, unprivileged_client, modern_cpu_for_migration):
    name = "vm-for-dual-stream-migration-metrics-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cpu_model=modern_cpu_for_migration,
        additional_labels=MIGRATION_POLICY_VM_LABEL,
        vm_affinity=request.param["vm_affinity"],
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def dual_stream_migration_metrics_vmim(
    request,
    admin_client,
    dual_stream_migration_metrics_vm,
):
    set_vm_affinity(vm=dual_stream_migration_metrics_vm, affinity=request.param["target_affinity"])
    with VirtualMachineInstanceMigration(
        name=dual_stream_migration_metrics_vm.name,
        namespace=dual_stream_migration_metrics_vm.namespace,
        vmi_name=dual_stream_migration_metrics_vm.vmi.name,
        client=admin_client,
    ) as vmim:
        vmim.wait_for_status(status=vmim.Status.RUNNING, timeout=TIMEOUT_3MIN)
        yield vmim


@pytest.fixture(scope="class")
def golden_image_data_source_for_dual_stream_scope_class(request, admin_client, golden_images_namespace):
    yield from get_or_create_golden_image_data_source(
        admin_client=admin_client, golden_images_namespace=golden_images_namespace, os_dict=request.param["os_dict"]
    )


@pytest.fixture(scope="class")
def golden_image_data_volume_template_for_dual_stream_scope_class(
    golden_image_data_source_for_dual_stream_scope_class,
):
    return get_data_volume_template_dict_with_default_storage_class(
        data_source=golden_image_data_source_for_dual_stream_scope_class
    )


@pytest.fixture(scope="class")
def dual_stream_start_end_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_dual_stream_scope_class,
    modern_cpu_for_migration,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_dual_stream_scope_class,
        vm_cpu_model=modern_cpu_for_migration,
        vm_affinity=request.param.get("vm_affinity"),
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def dual_stream_start_end_migration(request, admin_client, dual_stream_start_end_vm):
    set_vm_affinity(vm=dual_stream_start_end_vm, affinity=request.param["target_affinity"])
    migrate_vm_and_verify(vm=dual_stream_start_end_vm, client=admin_client, check_ssh_connectivity=True)
    return dual_stream_start_end_vm
