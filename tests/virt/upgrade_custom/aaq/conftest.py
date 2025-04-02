import pytest
from ocp_resources.application_aware_cluster_resource_quota import ApplicationAwareClusterResourceQuota
from ocp_resources.application_aware_resource_quota import ApplicationAwareResourceQuota
from ocp_resources.virtual_machine import VirtualMachine

from tests.virt.constants import AAQ_NAMESPACE_LABEL, ACRQ_NAMESPACE_LABEL
from tests.virt.upgrade_custom.aaq.constants import UPGRADE_QUOTA_FOR_ONE_VMI
from tests.virt.utils import enable_aaq_feature_gate, wait_for_virt_launcher_pod, wait_when_pod_in_gated_state
from utilities.infra import (
    create_ns,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
)


# AAQ Upgrade
@pytest.fixture(scope="session")
def enabled_aaq_feature_gate_scope_session(admin_client, hco_namespace, hyperconverged_resource_scope_session):
    with enable_aaq_feature_gate(
        client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_session,
        enable_acrq_support=True,
    ):
        yield


# ARQ
@pytest.fixture(scope="session")
def namespace_for_arq_upgrade_test():
    yield from create_ns(
        name="arq-upgrate-test-ns",
        labels=AAQ_NAMESPACE_LABEL,
    )


@pytest.fixture(scope="session")
def application_aware_resource_quota_upgrade(namespace_for_arq_upgrade_test):
    with ApplicationAwareResourceQuota(
        name="arq-for-upgrade-test",
        namespace=namespace_for_arq_upgrade_test.name,
        hard=UPGRADE_QUOTA_FOR_ONE_VMI,
    ) as arq:
        yield arq


@pytest.fixture(scope="session")
def vm_for_arq_upgrade_test(namespace_for_arq_upgrade_test, cpu_for_migration):
    vm_name = "vm-for-arq-upgrade-test"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_for_arq_upgrade_test.name,
        body=fedora_vm_body(name=vm_name),
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="session")
def vm_for_arq_upgrade_test_in_gated_state(namespace_for_arq_upgrade_test):
    vm_name = "vm-for-arq-upgrade-test-gated"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_for_arq_upgrade_test.name,
        body=fedora_vm_body(name=vm_name),
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
    ) as vm:
        vm.wait_for_specific_status(status=VirtualMachine.Status.STARTING)
        wait_for_virt_launcher_pod(vmi=vm.vmi)
        wait_when_pod_in_gated_state(pod=vm.vmi.virt_launcher_pod)
        yield vm


# ACRQ
@pytest.fixture(scope="session")
def namespace_for_acrq_upgrade_test():
    yield from create_ns(
        name="acrq-upgrate-test-ns",
        labels={**ACRQ_NAMESPACE_LABEL, **AAQ_NAMESPACE_LABEL},
    )


@pytest.fixture(scope="session")
def application_aware_cluster_resource_quota_upgrade():
    with ApplicationAwareClusterResourceQuota(
        name="acrq-for-upgrade-test",
        quota={"hard": UPGRADE_QUOTA_FOR_ONE_VMI},
        selector={"labels": {"matchLabels": ACRQ_NAMESPACE_LABEL}},
    ) as acrq:
        yield acrq


@pytest.fixture(scope="session")
def vm_for_acrq_upgrade_test(namespace_for_acrq_upgrade_test, cpu_for_migration):
    vm_name = "vm-for-acrq-upgrade-test"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_for_acrq_upgrade_test.name,
        body=fedora_vm_body(name=vm_name),
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="session")
def vm_for_acrq_upgrade_test_in_gated_state(namespace_for_acrq_upgrade_test):
    vm_name = "vm-for-acrq-upgrade-test-gated"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_for_acrq_upgrade_test.name,
        body=fedora_vm_body(name=vm_name),
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
    ) as vm:
        vm.wait_for_specific_status(status=VirtualMachine.Status.STARTING)
        wait_when_pod_in_gated_state(pod=vm.vmi.virt_launcher_pod)
        yield vm
