import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.virtual_machine_instance_migration import VirtualMachineInstanceMigration

from utilities.constants.timeouts import TIMEOUT_3MIN
from utilities.constants.virt import MIGRATION_POLICY_VM_LABEL
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm, set_vm_affinity


@pytest.fixture()
def dual_stream_migration_metrics_policy(admin_client):
    with MigrationPolicy(
        client=admin_client,
        name="dual-stream-migration-metrics-policy",
        bandwidth_per_migration="128Ki",
        allow_post_copy=False,
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as policy:
        yield policy


@pytest.fixture()
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
