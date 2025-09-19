import logging

import pytest

from tests.virt.node.migration_and_maintenance.utils import assert_multifd_capability_in_logs

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
