"""
Tests for virt-launcher pod log verbosity and migration progress keys.
"""

import logging

import pytest
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.node.log_verbosity.constants import (
    VIRT_LOG_VERBOSITY_LEVEL_6,
)
from utilities.constants import MIGRATION_POLICY_VM_LABEL, TIMEOUT_1MIN, TIMEOUT_5SEC
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    running_vm,
)

LOGGER = logging.getLogger(__name__)


def find_missing_progress_keys_in_pod_log(pod):
    """
    Return a list of migration progress keys missing from the pod's log.
    """
    pod_log = pod.log(container="compute")
    missing_keys = list(
        filter(
            lambda key: key not in pod_log,
            [
                "TimeElapsed",
                "DataProcessed",
                "DataRemaining",
                "DataTotal",
                "MemoryProcessed",
                "MemoryRemaining",
                "MemoryTotal",
                "MemoryBandwidth",
                "DirtyRate",
                "Iteration",
                "PostcopyRequests",
                "ConstantPages",
                "NormalPages",
                "NormalData",
                "ExpectedDowntime",
                "DiskMbps",
            ],
        )
    )
    return missing_keys


def wait_for_all_progress_keys_in_pod_log(pod):
    """
    Wait until all migration progress keys are present in the pod's log.
    Raises TimeoutExpiredError if not all keys are found within the timeout.
    """
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=find_missing_progress_keys_in_pod_log,
        pod=pod,
    )
    missing_keys = None
    try:
        for missing_keys in samples:
            if not missing_keys:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"The following progress keys are missing: {missing_keys}")
        raise


@pytest.fixture(scope="class")
def vm_for_migration_progress_test(
    namespace,
    unprivileged_client,
    cpu_for_migration,
):
    """
    Fixture to create and start a VM for migration progress tests.
    """
    name = "vm-for-migration-progress-test"
    with VirtualMachineForTests(
        name=name,
        client=unprivileged_client,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        additional_labels=MIGRATION_POLICY_VM_LABEL,
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def source_pod_log_verbosity_test(vm_for_migration_progress_test):
    """
    Fixture to get the virt-launcher pod for the test VM.
    """
    return vm_for_migration_progress_test.vmi.virt_launcher_pod


@pytest.fixture()
def migrated_vm_with_policy(migration_policy_with_bandwidth, vm_for_migration_progress_test):
    """
    Fixture to migrate the test VM with a migration policy.
    """
    migrate_vm_and_verify(vm=vm_for_migration_progress_test, wait_for_migration_success=False)


@pytest.mark.parametrize(
    "updated_log_verbosity_config",
    [
        pytest.param("component"),
    ],
    indirect=True,
)
class TestProgressOfMigrationInVirtLauncher:
    @pytest.mark.polarion("CNV-9057")
    def test_virt_launcher_log_verbosity(
        self,
        updated_log_verbosity_config,
        vm_for_migration_progress_test,
    ):
        """
        Test that virt-launcher pod log contains the correct verbosity level.
        """
        assert f"verbosity to {VIRT_LOG_VERBOSITY_LEVEL_6}" in vm_for_migration_progress_test.vmi.virt_launcher_pod.log(
            container="compute"
        ), f"Not found correct log verbosity level: {VIRT_LOG_VERBOSITY_LEVEL_6} in logs"

    @pytest.mark.rwx_default_storage
    @pytest.mark.polarion("CNV-9058")
    def test_progress_of_vm_migration_in_virt_launcher_pod(
        self,
        updated_log_verbosity_config,
        vm_for_migration_progress_test,
        source_pod_log_verbosity_test,
        migrated_vm_with_policy,
    ):
        """
        Test that all migration progress keys appear in virt-launcher pod log after migration.
        """
        wait_for_all_progress_keys_in_pod_log(pod=source_pod_log_verbosity_test)
