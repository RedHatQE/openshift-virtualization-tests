import logging

import pytest

from tests.virt.cluster.aaq.utils import check_arq_status_values_different_allocations
from utilities.virt import migrate_vm_and_verify

LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestAAQDifferentAllocationMethods"

pytestmark = pytest.mark.usefixtures(
    "enabled_aaq_in_hco_scope_package",
    "updated_namespace_with_aaq_label",
)


@pytest.mark.usefixtures(
    "updated_aaq_allocation_method",
)
class TestAAQDifferentAllocationMethods:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_aaq_allocation_methods")
    @pytest.mark.polarion("CNV-11242")
    def test_aaq_with_virtual_resources_allocation_methods(
        self,
        aaq_allocation_methods_matrix__class__,
        application_aware_resource_quota,
        vm_for_aaq_allocation_methods_test,
    ):
        check_arq_status_values_different_allocations(
            arq=application_aware_resource_quota,
            vm=vm_for_aaq_allocation_methods_test,
            allocation_method=aaq_allocation_methods_matrix__class__,
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_aaq_allocation_methods"])
    @pytest.mark.polarion("CNV-11387")
    def test_aaq_vm_migration_with_different_allocation(
        self,
        skip_if_no_common_cpu,
        vm_for_aaq_allocation_methods_test,
    ):
        migrate_vm_and_verify(vm=vm_for_aaq_allocation_methods_test)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_aaq_allocation_methods"])
    @pytest.mark.polarion("CNV-11248")
    def test_aaq_different_allocation_memory_overcommit(
        self,
        aaq_allocation_methods_matrix__class__,
        application_aware_resource_quota,
        updated_hco_memory_overcommit,
        restarted_vm_for_aaq_allocation_methods_test,
    ):
        check_arq_status_values_different_allocations(
            arq=application_aware_resource_quota,
            vm=restarted_vm_for_aaq_allocation_methods_test,
            allocation_method=aaq_allocation_methods_matrix__class__,
        )
