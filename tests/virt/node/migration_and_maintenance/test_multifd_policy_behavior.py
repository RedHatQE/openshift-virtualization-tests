import logging

import pytest

LOGGER = logging.getLogger(__name__)


@pytest.mark.usefixtures("updated_multifd_vm_log_verbosity_config")
class TestMultifdBehavior:
    @pytest.mark.polarion("CNV-12266")
    def test_multifd_disabled_with_postcopy_policy(
        self,
        vm_for_multifd_test,
        migration_policy_postcopy,
        migrated_vm_source_pod,
    ):
        # Check logs do NOT contain multifd capability
        log_content = migrated_vm_source_pod.log(container="compute")
        assert "Enabling migration capability 'multifd'" not in log_content, (
            "multifd should be disabled with postcopy policy"
        )

    @pytest.mark.polarion("CNV-12262")
    def test_multifd_enabled_baseline(
        self,
        vm_for_multifd_test,
        migrated_vm_source_pod,
    ):
        # Check logs DO contain multifd capability
        log_content = migrated_vm_source_pod.log(container="compute")
        assert "Enabling migration capability 'multifd'" in log_content, (
            "multifd should be enabled in baseline scenario"
        )

    @pytest.mark.polarion("CNV-12265")
    def test_multifd_disabled_with_cpu_limit(
        self,
        vm_for_multifd_test,
        added_vm_cpu_limit,
        migrated_vm_source_pod,
    ):
        # Check logs do NOT contain multifd capability
        log_content = migrated_vm_source_pod.log(container="compute")
        assert "Enabling migration capability 'multifd'" not in log_content, "multifd should be disabled with CPU limit"
