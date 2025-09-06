import logging

import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.resource import ResourceEditor

from utilities.constants import MIGRATION_POLICY_VM_LABEL
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def vm_for_multifd_test(
    namespace,
    admin_client,
    unprivileged_client,
    cpu_for_migration,
):
    name = "vm-for-multifd-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        additional_labels=MIGRATION_POLICY_VM_LABEL,
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def migration_policy_postcopy():
    with MigrationPolicy(
        name="multifd-postcopy-policy",
        allow_post_copy=True,
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as mp:
        yield mp


@pytest.fixture()
def migrated_vm_with_postcopy(vm_for_multifd_test, migration_policy_postcopy):
    source_pod = vm_for_multifd_test.vmi.virt_launcher_pod
    migrate_vm_and_verify(vm=vm_for_multifd_test, wait_for_migration_success=True)
    return source_pod


@pytest.fixture()
def migrated_vm_baseline(vm_for_multifd_test):
    # No migration policy - baseline behavior
    source_pod = vm_for_multifd_test.vmi.virt_launcher_pod
    migrate_vm_and_verify(vm=vm_for_multifd_test, wait_for_migration_success=True)
    return source_pod


@pytest.fixture()
def add_vm_cpu_limit(vm_for_multifd_test):
    # Add CPU limits to VM template spec
    ResourceEditor({
        vm_for_multifd_test: {"spec": {"template": {"spec": {"domain": {"resources": {"limits": {"cpu": "2"}}}}}}}
    }).update()

    # Restart VM so CPU limits take effect
    restart_vm_wait_for_running_vm(vm=vm_for_multifd_test, wait_for_interfaces=True)
    return vm_for_multifd_test


@pytest.fixture()
def migrated_vm_with_cpu_limit(add_vm_cpu_limit):
    # Capture source pod before migration (after CPU limits applied)
    source_pod = add_vm_cpu_limit.vmi.virt_launcher_pod

    # Perform migration
    migrate_vm_and_verify(vm=add_vm_cpu_limit, wait_for_migration_success=True)
    return source_pod


class TestMultifdBehavior:
    @pytest.mark.polarion("CNV-12266")
    def test_multifd_disabled_with_postcopy_policy(
        self,
        updated_multifd_vm_log_verbosity_config,
        vm_for_multifd_test,
        migration_policy_postcopy,
        migrated_vm_with_postcopy,
    ):
        # Check logs do NOT contain multifd capability
        log_content = migrated_vm_with_postcopy.log(container="compute")
        assert "Enabling migration capability 'multifd'" not in log_content, (
            "multifd should be disabled with postcopy policy"
        )

    @pytest.mark.polarion("CNV-12262")
    def test_multifd_enabled_baseline(
        self,
        updated_multifd_vm_log_verbosity_config,
        vm_for_multifd_test,
        migrated_vm_baseline,
    ):
        # Check logs DO contain multifd capability
        log_content = migrated_vm_baseline.log(container="compute")
        assert "Enabling migration capability 'multifd'" in log_content, (
            "multifd should be enabled in baseline scenario"
        )

    @pytest.mark.polarion("CNV-12265")
    def test_multifd_disabled_with_cpu_limit(
        self,
        updated_multifd_vm_log_verbosity_config,
        vm_for_multifd_test,
        add_vm_cpu_limit,
        migrated_vm_with_cpu_limit,
    ):
        # Check logs do NOT contain multifd capability
        log_content = migrated_vm_with_cpu_limit.log(container="compute")
        assert "Enabling migration capability 'multifd'" not in log_content, "multifd should be disabled with CPU limit"
