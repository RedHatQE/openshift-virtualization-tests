import logging

import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.virtual_machine_instance_migration import VirtualMachineInstanceMigration

from utilities.constants.timeouts import TIMEOUT_3MIN
from utilities.constants.virt import MIGRATION_POLICY_VM_LABEL

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def migration_policy_with_bandwidth():
    with MigrationPolicy(
        name="migration-policy",
        bandwidth_per_migration="128Ki",
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as mp:
        yield mp


@pytest.fixture(scope="class")
def migration_policy_with_bandwidth_scope_class():
    with MigrationPolicy(
        name="migration-policy",
        bandwidth_per_migration="128Ki",
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as mp:
        yield mp


@pytest.fixture(scope="class")
def migrated_vm_multiple_times(request, vm_for_migration_test):
    vmim = []
    for migration_index in range(request.param):
        migration_obj = VirtualMachineInstanceMigration(
            name=f"{vm_for_migration_test.name}-{migration_index}",
            namespace=vm_for_migration_test.namespace,
            vmi_name=vm_for_migration_test.vmi.name,
            teardown=False,
        )
        migration_obj.deploy(wait=True)
        migration_obj.wait_for_status(status=migration_obj.Status.SUCCEEDED, timeout=TIMEOUT_3MIN)
        vmim.append(migration_obj)
        LOGGER.info(f"Migration #{migration_index + 1} done")
    yield
    for mig_obj in vmim:
        mig_obj.clean_up()
