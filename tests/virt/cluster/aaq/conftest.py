import logging

import pytest
from ocp_resources.application_aware_cluster_resource_quota import ApplicationAwareClusterResourceQuota
from ocp_resources.application_aware_resource_quota import ApplicationAwareResourceQuota
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.utils import clean_up_migration_jobs, hotplug_resource_and_wait_hotplug_migration_finish, hotplug_spec_vm
from tests.virt.cluster.aaq.constants import (
    ACRQ_QUOTA_HARD_SPEC,
    ARQ_QUOTA_HARD_SPEC,
    CPU_MAX_SOCKETS,
    MEMORY_MAX_GUEST,
    POD_RESOURCES_SPEC,
    VM_CPU_CORES,
    VM_MEMORY_GUEST,
)
from tests.virt.cluster.aaq.utils import (
    wait_for_aacrq_object_created,
)
from tests.virt.constants import AAQ_NAMESPACE_LABEL, ACRQ_NAMESPACE_LABEL, ACRQ_TEST
from tests.virt.utils import enable_aaq_feature_gate, wait_when_pod_in_gated_state
from utilities.constants import (
    POD_CONTAINER_SPEC,
    POD_SECURITY_CONTEXT_SPEC,
    TIMEOUT_1MIN,
    TIMEOUT_5SEC,
    Images,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import create_ns, get_pod_by_name_prefix, label_project
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    get_created_migration_job,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
)

LOGGER = logging.getLogger(__name__)


# AAQ - ApplicationAwareQuota, operator for managing resource quotas per component
@pytest.fixture(scope="package")
def enabled_aaq_feature_gate_scope_package(admin_client, hco_namespace, hyperconverged_resource_scope_package):
    with enable_aaq_feature_gate(
        client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_package,
    ):
        yield


@pytest.fixture(scope="module")
def updated_namespace_with_aaq_label(admin_client, namespace):
    label_project(name=namespace.name, label=AAQ_NAMESPACE_LABEL, admin_client=admin_client)


@pytest.fixture(scope="class")
def updated_aaq_allocation_method(hyperconverged_resource_scope_class, aaq_allocation_methods_matrix__class__):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "applicationAwareConfig": {"vmiCalcConfigName": aaq_allocation_methods_matrix__class__},
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def updated_hco_memory_overcommit(hyperconverged_resource_scope_class):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "higherWorkloadDensity": {"memoryOvercommitPercentage": 50},
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="class")
def first_pod_for_aaq_test(namespace):
    with Pod(
        name="first-pod-for-aaq-test",
        namespace=namespace.name,
        security_context=POD_SECURITY_CONTEXT_SPEC,
        containers=[{**POD_CONTAINER_SPEC, **POD_RESOURCES_SPEC}],
    ) as pod:
        pod.wait_for_status(status=Pod.Status.RUNNING)
        yield pod


@pytest.fixture(scope="class")
def second_pod_for_aaq_test_in_gated_state(namespace):
    with Pod(
        name="second-pod-for-aaq-test",
        namespace=namespace.name,
        security_context=POD_SECURITY_CONTEXT_SPEC,
        containers=[{**POD_CONTAINER_SPEC, **POD_RESOURCES_SPEC}],
    ) as pod:
        wait_when_pod_in_gated_state(pod=pod)
        yield pod


@pytest.fixture(scope="class")
def vm_for_aaq_test(namespace, unprivileged_client, cpu_for_migration):
    vm_name = "first-vm-for-aaq-test"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        cpu_cores=VM_CPU_CORES,
        memory_guest=VM_MEMORY_GUEST,
        body=fedora_vm_body(name=vm_name),
        client=unprivileged_client,
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def vm_for_aaq_test_in_gated_state(namespace, unprivileged_client):
    vm_name = "second-vm-for-aaq-test"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        cpu_cores=VM_CPU_CORES,
        memory_guest=VM_MEMORY_GUEST,
        body=fedora_vm_body(name=vm_name),
        client=unprivileged_client,
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
    ) as vm:
        vm.wait_for_specific_status(status=VirtualMachine.Status.STARTING)
        wait_when_pod_in_gated_state(pod=vm.vmi.virt_launcher_pod)
        yield vm


# ARQ - ApplicationAwareResourceQuota, namespaced object containing quotas for resources
@pytest.fixture(scope="class")
def application_aware_resource_quota(namespace):
    with ApplicationAwareResourceQuota(
        name="application-aware-resource-quota-for-aaq-test",
        namespace=namespace.name,
        hard=ARQ_QUOTA_HARD_SPEC,
    ) as arq:
        yield arq


@pytest.fixture()
def updated_arq_quota(request, namespace, application_aware_resource_quota):
    ResourceEditor({
        application_aware_resource_quota: {
            "spec": {
                "hard": request.param["hard"],
            }
        },
    }).update()


@pytest.fixture()
def migrated_arq_vm(vm_for_aaq_test):
    migrate_vm_and_verify(vm=vm_for_aaq_test)


# ACRQ - ApplicationAwareClusterResourceQuota, cluster level object containing quotas for multiple resources
@pytest.fixture(scope="module")
def enabled_acrq_support(admin_client, hco_namespace, hyperconverged_resource_scope_module):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: {
                "spec": {
                    "applicationAwareConfig": {"allowApplicationAwareClusterResourceQuota": True},
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="class")
def application_aware_cluster_resource_quota():
    with ApplicationAwareClusterResourceQuota(
        name="application-aware-cluster-resource-quota-for-aaq-test",
        quota={"hard": ACRQ_QUOTA_HARD_SPEC},
        selector={"labels": {"matchLabels": ACRQ_NAMESPACE_LABEL}},
    ) as acrq:
        yield acrq


@pytest.fixture(scope="class")
def acrq_label_on_first_namespace(admin_client, namespace, application_aware_cluster_resource_quota):
    label_project(name=namespace.name, label=ACRQ_NAMESPACE_LABEL, admin_client=admin_client)
    wait_for_aacrq_object_created(namespace=namespace, acrq_name=application_aware_cluster_resource_quota.name)


@pytest.fixture(scope="class")
def second_namespace_for_acrq_test():
    yield from create_ns(
        name="acrq-test-second-ns",
        labels={**ACRQ_NAMESPACE_LABEL, **AAQ_NAMESPACE_LABEL},
    )


@pytest.fixture()
def removed_acrq_label_from_second_namespace(second_namespace_for_acrq_test):
    with ResourceEditor(patches={second_namespace_for_acrq_test: {"metadata": {"labels": {ACRQ_TEST: None}}}}):
        yield


@pytest.fixture(scope="class")
def vm_in_second_namespace_for_acrq_test(second_namespace_for_acrq_test):
    vm_name = "vm-another-namespace-for-acrq-test"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=second_namespace_for_acrq_test.name,
        cpu_cores=VM_CPU_CORES,
        memory_guest=VM_MEMORY_GUEST,
        body=fedora_vm_body(name=vm_name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def hotplug_vm_for_aaq_test(namespace, unprivileged_client, cpu_for_migration):
    with VirtualMachineForTests(
        name="hotplug-vm-for-aaq-test",
        namespace=namespace.name,
        cpu_max_sockets=CPU_MAX_SOCKETS,
        memory_max_guest=MEMORY_MAX_GUEST,
        cpu_sockets=1,
        memory_guest="1Gi",
        image=Images.Fedora.FEDORA_CONTAINER_IMAGE,
        client=unprivileged_client,
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def hotplugged_resource(request, unprivileged_client, hotplug_vm_for_aaq_test, admin_client):
    hotplug_resource_and_wait_hotplug_migration_finish(
        vm=hotplug_vm_for_aaq_test,
        client=unprivileged_client,
        sockets=request.param.get("sockets"),
        memory_guest=request.param.get("memory_guest"),
    )
    yield
    clean_up_migration_jobs(client=admin_client, vm=hotplug_vm_for_aaq_test)


@pytest.fixture()
def hotplugged_resource_exceeding_quota(request, hotplug_vm_for_aaq_test):
    hotplug_spec_vm(
        vm=hotplug_vm_for_aaq_test, sockets=request.param.get("sockets"), memory_guest=request.param.get("memory_guest")
    )
    get_created_migration_job(vm=hotplug_vm_for_aaq_test)


@pytest.fixture()
def hotplugged_target_pod(namespace, unprivileged_client, hotplug_vm_for_aaq_test):
    # VMIM/VMI do not have target pod in the spec when it is in gated state. Filter out running pods.
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=get_pod_by_name_prefix,
        pod_prefix=f"virt-launcher-{hotplug_vm_for_aaq_test.name}",
        namespace=namespace.name,
        get_all=True,
        dyn_client=unprivileged_client,
    )
    sample = []
    try:
        for sample in sampler:
            if sample:
                for pod in sample:
                    if pod.status not in (Pod.Status.RUNNING, Pod.Status.COMPLETED, Pod.Status.SUCCEEDED):
                        return pod
    except TimeoutExpiredError:
        LOGGER.error(
            "Not found pods in non-running state.\n "
            f"Current pods: {', '.join(f'{pod.name} - {pod.status}' for pod in sample)}"
        )
        raise


@pytest.fixture(scope="class")
def vm_for_aaq_allocation_methods_test(namespace, cpu_for_migration, aaq_allocation_methods_matrix__class__):
    vm_name = f"vm-aaq-test-{aaq_allocation_methods_matrix__class__.lower()}-allocation"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        cpu_limits=1,
        memory_limits="1Gi",
        body=fedora_vm_body(name=vm_name),
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def restarted_vm_for_aaq_allocation_methods_test(vm_for_aaq_allocation_methods_test):
    yield restart_vm_wait_for_running_vm(
        vm=vm_for_aaq_allocation_methods_test, wait_for_interfaces=False, check_ssh_connectivity=False
    )
