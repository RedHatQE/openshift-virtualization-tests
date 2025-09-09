import logging

import pytest

LOGGER = logging.getLogger(__name__)

MULTIFD_LOG_MESSAGE = "Enabling migration capability 'multifd'"


def assert_multifd_capability_in_logs(source_pod, expected_in_log):
    message_in_log = MULTIFD_LOG_MESSAGE in source_pod.log(container="compute")
    assert message_in_log == expected_in_log, f"multifd should be {'enabled' if expected_in_log else 'disabled'}"


@pytest.mark.usefixtures("updated_multifd_vm_log_verbosity_config")
class TestMultifdBehavior:
    @pytest.mark.polarion("CNV-12266")
    def test_multifd_disabled_with_postcopy_policy(
        self,
        vm_for_multifd_test,
        migration_policy_postcopy,
        migrated_vm_source_pod,
    ):
        assert_multifd_capability_in_logs(source_pod=migrated_vm_source_pod, expected_in_log=False)

    @pytest.mark.polarion("CNV-12262")
    def test_multifd_enabled_default(
        self,
        vm_for_multifd_test,
        migrated_vm_source_pod,
    ):
        assert_multifd_capability_in_logs(source_pod=migrated_vm_source_pod, expected_in_log=True)

    @pytest.mark.polarion("CNV-12265")
    def test_multifd_disabled_with_cpu_limit(
        self,
        vm_for_multifd_test,
        added_vm_cpu_limit,
        migrated_vm_source_pod,
    ):
        assert_multifd_capability_in_logs(source_pod=migrated_vm_source_pod, expected_in_log=False)
