import logging

import pytest

LOGGER = logging.getLogger(__name__)

# Constants
MULTIFD_LOG_MESSAGE = "Enabling migration capability 'multifd'"


def assert_multifd_capability_in_logs(source_pod, expected_in_log: bool, scenario_name: str):
    log_content = source_pod.log(container="compute")

    if expected_in_log:
        assert MULTIFD_LOG_MESSAGE in log_content, f"multifd should be enabled in {scenario_name}"
    else:
        assert MULTIFD_LOG_MESSAGE not in log_content, f"multifd should be disabled with {scenario_name}"


@pytest.mark.parametrize("updated_log_verbosity_config", ["virtLauncher"], indirect=True)
@pytest.mark.usefixtures("updated_log_verbosity_config")
class TestMultifdBehavior:
    @pytest.mark.polarion("CNV-12266")
    def test_multifd_disabled_with_postcopy_policy(
        self,
        vm_for_multifd_test,
        migration_policy_postcopy,
        migrated_vm_source_pod,
    ):
        assert_multifd_capability_in_logs(
            source_pod=migrated_vm_source_pod, expected_in_log=False, scenario_name="postcopy policy"
        )

    @pytest.mark.polarion("CNV-12262")
    def test_multifd_enabled_baseline(
        self,
        vm_for_multifd_test,
        migrated_vm_source_pod,
    ):
        assert_multifd_capability_in_logs(
            source_pod=migrated_vm_source_pod, expected_in_log=True, scenario_name="baseline scenario"
        )

    @pytest.mark.polarion("CNV-12265")
    def test_multifd_disabled_with_cpu_limit(
        self,
        vm_for_multifd_test,
        added_vm_cpu_limit,
        migrated_vm_source_pod,
    ):
        assert_multifd_capability_in_logs(
            source_pod=migrated_vm_source_pod, expected_in_log=False, scenario_name="CPU limit"
        )
