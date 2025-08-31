import logging

import pytest
from ocp_resources.migration_policy import MigrationPolicy

from tests.utils import clean_up_migration_jobs
from utilities.constants import MIGRATION_POLICY_VM_LABEL
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    running_vm,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="function")
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
        # Clean up migration jobs before stopping the VM to avoid cleanup issues
        clean_up_migration_jobs(client=admin_client, vm=vm)


@pytest.fixture(scope="function")
def vm_for_multifd_test_with_cpu_limit(
    namespace,
    admin_client,
    unprivileged_client,
    cpu_for_migration,
):
    name = "vm-for-multifd-test-cpu-limit"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        additional_labels=MIGRATION_POLICY_VM_LABEL,
        cpu_model=cpu_for_migration,
        cpu_limits="1",  # CPU limit to disable multifd
    ) as vm:
        running_vm(vm=vm)
        yield vm
        # Clean up migration jobs before stopping the VM to avoid cleanup issues
        clean_up_migration_jobs(client=admin_client, vm=vm)


@pytest.fixture()
def source_pod_for_multifd_test(vm_for_multifd_test):
    return vm_for_multifd_test.vmi.virt_launcher_pod


@pytest.fixture()
def source_pod_for_multifd_test_with_cpu_limit(vm_for_multifd_test_with_cpu_limit):
    return vm_for_multifd_test_with_cpu_limit.vmi.virt_launcher_pod


@pytest.fixture(scope="function")
def migration_policy_postcopy():
    with MigrationPolicy(
        name="multifd-postcopy-policy",
        allow_post_copy=True,
        vmi_selector=MIGRATION_POLICY_VM_LABEL,  # Match VM labels
    ) as mp:
        yield mp


# Sets cluster-wide log verbosity to level 6 for all VMs in this test class
@pytest.mark.parametrize(
    "updated_log_verbosity_config",
    [
        pytest.param("component"),
    ],
    indirect=True,
)
class TestMultifdBehavior:
    @pytest.mark.rwx_default_storage
    @pytest.mark.polarion("CNV-12262")
    def test_multifd_enabled_baseline(
        self,
        updated_log_verbosity_config,
        vm_for_multifd_test,
        source_pod_for_multifd_test,
    ):
        # Perform migration without restrictions (baseline) and wait for completion
        migrate_vm_and_verify(vm=vm_for_multifd_test, wait_for_migration_success=True)

        # Check logs DO contain multifd capability
        log_content = source_pod_for_multifd_test.log(container="compute")
        assert "Enabling migration capability 'multifd'" in log_content, (
            "multifd should be enabled in baseline scenario"
        )

    @pytest.mark.rwx_default_storage
    @pytest.mark.polarion("CNV-12265")
    def test_multifd_disabled_with_cpu_limit(
        self,
        updated_log_verbosity_config,
        vm_for_multifd_test_with_cpu_limit,
        source_pod_for_multifd_test_with_cpu_limit,
    ):
        # Perform migration and wait for completion
        migrate_vm_and_verify(vm=vm_for_multifd_test_with_cpu_limit, wait_for_migration_success=True)

        # Check logs do NOT contain multifd capability
        log_content = source_pod_for_multifd_test_with_cpu_limit.log(container="compute")
        assert "Enabling migration capability 'multifd'" not in log_content, "multifd should be disabled with CPU limit"

    @pytest.mark.rwx_default_storage
    @pytest.mark.polarion("CNV-12266")
    def test_multifd_disabled_with_postcopy_policy(
        self,
        updated_log_verbosity_config,
        vm_for_multifd_test,
        source_pod_for_multifd_test,
        migration_policy_postcopy,
    ):
        # Perform migration with postcopy policy and wait for completion
        migrate_vm_and_verify(vm=vm_for_multifd_test, wait_for_migration_success=True)

        # Check logs do NOT contain multifd capability
        log_content = source_pod_for_multifd_test.log(container="compute")
        assert "Enabling migration capability 'multifd'" not in log_content, (
            "multifd should be disabled with postcopy policy"
        )
