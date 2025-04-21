import logging

import pytest

from tests.virt.cluster.aaq.constants import QUOTA_FOR_TWO_VMI
from tests.virt.utils import check_arq_status_values
from utilities.virt import wait_for_running_vm

LOGGER = logging.getLogger(__name__)

TESTS_ACRQ_CLASS_NAME = "TestApplicationAwareClusterResourceQuota"


@pytest.mark.usefixtures(
    "enabled_aaq_in_hco_scope_package",
    "enabled_acrq_support",
    "updated_namespace_with_aaq_label",
    "application_aware_cluster_resource_quota",
    "acrq_label_on_first_namespace",
    "vm_for_aaq_test",
    "vm_in_second_namespace_for_acrq_test",
    "vm_for_aaq_test_in_gated_state",
)
class TestApplicationAwareClusterResourceQuota:
    @pytest.mark.dependency(name=f"{TESTS_ACRQ_CLASS_NAME}::vm_gated")
    @pytest.mark.polarion("CNV-11241")
    def test_acrq_can_manage_vms_in_multiple_namespaces(
        self,
        application_aware_cluster_resource_quota,
    ):
        check_arq_status_values(
            current_values=application_aware_cluster_resource_quota.instance.status.total.used,
            expected_values=QUOTA_FOR_TWO_VMI,
        )

    @pytest.mark.dependency(depends=[f"{TESTS_ACRQ_CLASS_NAME}::vm_gated"])
    @pytest.mark.polarion("CNV-11284")
    def test_acrq_gated_vm_started_when_namespace_label_removed(
        self,
        vm_for_aaq_test_in_gated_state,
        removed_acrq_label_from_second_namespace,
    ):
        wait_for_running_vm(vm=vm_for_aaq_test_in_gated_state)
