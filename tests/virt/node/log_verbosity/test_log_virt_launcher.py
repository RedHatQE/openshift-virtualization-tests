import logging

import pytest
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.utils import clean_up_migration_jobs
from tests.virt.node.log_verbosity.constants import (
    VIRT_LOG_VERBOSITY_LEVEL_6,
)
from tests.virt.utils import is_jira_67515_open
from utilities.constants import MIGRATION_POLICY_VM_LABEL, TIMEOUT_1MIN, TIMEOUT_5SEC
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    running_vm,
)

LOGGER = logging.getLogger(__name__)


def find_missing_progress_keys_in_pod_log(pod):
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
    admin_client,
    unprivileged_client,
    cpu_for_migration,
):
    name = "vm-for-migration-progress-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        additional_labels=MIGRATION_POLICY_VM_LABEL,
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm
        # Due to the bug - migration job should be removed before stopping the VM
        if is_jira_67515_open():
            clean_up_migration_jobs(client=admin_client, vm=vm)


@pytest.fixture()
def source_pod_log_verbosity_test(vm_for_migration_progress_test):
    return vm_for_migration_progress_test.vmi.virt_launcher_pod


@pytest.fixture()
def migrated_vm_with_policy(migration_policy_with_bandwidth, vm_for_migration_progress_test):
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
        wait_for_all_progress_keys_in_pod_log(pod=source_pod_log_verbosity_test)
