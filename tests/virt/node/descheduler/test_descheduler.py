import logging

import pytest
from ocp_resources.resource import ResourceEditor

from tests.virt.node.descheduler.constants import DESCHEDULER_TEST_LABEL
from tests.virt.node.descheduler.utils import (
    assert_vms_consistent_virt_launcher_pods,
    assert_vms_distribution_after_failover,
    verify_at_least_one_vm_migrated,
)
from tests.virt.utils import verify_guest_boot_time

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.tier3,
    pytest.mark.descheduler,
    pytest.mark.post_upgrade,
    pytest.mark.usefixtures(
        "descheduler_long_lifecycle_profile",
    ),
]

NO_MIGRATION_STORM_ASSERT_MESSAGE = "Verify no migration storm after triggered migrations by the descheduler."


@pytest.mark.parametrize(
    "calculated_vm_deployment_for_descheduler_test",
    [pytest.param(0.50)],
    indirect=True,
)
class TestDeschedulerEvictsVMAfterDrainUncordon:
    TESTS_CLASS_NAME = "TestDeschedulerEvictsVMAfterDrainUncordon"

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_descheduler_evicts_vm_after_drain_uncordon")
    @pytest.mark.polarion("CNV-5922")
    def test_descheduler_evicts_vm_after_drain_uncordon(
        self,
        schedulable_nodes,
        deployed_vms_for_descheduler_test,
        vms_boot_time_before_node_drain,
        drain_uncordon_node,
    ):
        assert_vms_distribution_after_failover(
            vms=deployed_vms_for_descheduler_test,
            nodes=schedulable_nodes,
        )

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_no_migrations_storm",
        depends=[f"{TESTS_CLASS_NAME}::test_descheduler_evicts_vm_after_drain_uncordon"],
    )
    @pytest.mark.polarion("CNV-7316")
    def test_no_migrations_storm(
        self,
        deployed_vms_for_descheduler_test,
        all_existing_migrations_completed,
    ):
        LOGGER.info(NO_MIGRATION_STORM_ASSERT_MESSAGE)
        assert_vms_consistent_virt_launcher_pods(running_vms=deployed_vms_for_descheduler_test)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_no_migrations_storm"])
    @pytest.mark.polarion("CNV-8288")
    def test_boot_time_after_migrations_complete(
        self,
        deployed_vms_for_descheduler_test,
        vms_boot_time_before_node_drain,
    ):
        verify_guest_boot_time(
            vm_list=deployed_vms_for_descheduler_test,
            initial_boot_time=vms_boot_time_before_node_drain,
        )


@pytest.mark.parametrize(
    "calculated_vm_deployment_for_node_with_least_available_memory, deployed_vms_for_utilization_imbalance",
    [
        pytest.param(
            0.30,
            {
                "vm_prefix": "with-annotation-imbalance",
                "descheduler_eviction": True,
            },
        )
    ],
    indirect=True,
)
class TestDeschedulerEvictsVMFromUtilizationImbalance:
    TESTS_CLASS_NAME = "TestDeschedulerEvictsVMFromUtilizationImbalance"

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_descheduler_evicts_vm_from_utilization_imbalance")
    @pytest.mark.polarion("CNV-8217")
    def test_descheduler_evicts_vm_from_utilization_imbalance(
        self,
        node_with_least_available_memory,
        node_with_min_memory_labeled_for_descheduler_test,
        deployed_vms_for_utilization_imbalance,
        vms_boot_time_before_utilization_imbalance,
        utilization_imbalance,
        node_with_max_memory_labeled_for_descheduler_test,
    ):
        verify_at_least_one_vm_migrated(
            vms=deployed_vms_for_utilization_imbalance, node_before=node_with_least_available_memory
        )

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::test_no_migrations_storm",
        depends=[f"{TESTS_CLASS_NAME}::test_descheduler_evicts_vm_from_utilization_imbalance"],
    )
    @pytest.mark.polarion("CNV-8918")
    def test_no_migrations_storm(
        self,
        deployed_vms_for_utilization_imbalance,
        all_existing_migrations_completed,
    ):
        LOGGER.info(NO_MIGRATION_STORM_ASSERT_MESSAGE)
        assert_vms_consistent_virt_launcher_pods(running_vms=deployed_vms_for_utilization_imbalance)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_no_migrations_storm"])
    @pytest.mark.polarion("CNV-8919")
    def test_boot_time_after_migrations_complete(
        self,
        deployed_vms_for_utilization_imbalance,
        vms_boot_time_before_utilization_imbalance,
    ):
        verify_guest_boot_time(
            vm_list=deployed_vms_for_utilization_imbalance,
            initial_boot_time=vms_boot_time_before_utilization_imbalance,
        )


@pytest.mark.parametrize(
    "calculated_vm_deployment_for_node_with_least_available_memory, deployed_vms_for_utilization_imbalance",
    [
        pytest.param(
            0.80,
            {
                "vm_prefix": "no-annotation-imbalance",
                "descheduler_eviction": False,
            },
        )
    ],
    indirect=True,
)
class TestDeschedulerDoesNotEvictVMWithNoAnnotationFromUtilizationImbalance:
    @pytest.mark.polarion("CNV-8920")
    def test_descheduler_does_not_evict_vm_with_no_annotation_from_utilization_imbalance(
        self,
        node_with_min_memory_labeled_for_descheduler_test,
        deployed_vms_for_utilization_imbalance,
    ):
        assert_vms_consistent_virt_launcher_pods(running_vms=deployed_vms_for_utilization_imbalance)


@pytest.mark.parametrize(
    "calculated_vm_deployment_for_node_with_least_available_memory",
    [pytest.param(0.80)],
    indirect=True,
)
class TestDeschedulerNodeLabel:
    @pytest.mark.polarion("CNV-7415")
    def test_descheduler_node_labels(
        self,
        node_with_least_available_memory,
        node_with_min_memory_labeled_for_descheduler_test,
        node_with_most_available_memory,
        deployed_vms_on_labeled_node,
    ):
        with ResourceEditor(
            patches={node_with_most_available_memory: {"metadata": {"labels": DESCHEDULER_TEST_LABEL}}}
        ):
            verify_at_least_one_vm_migrated(
                vms=deployed_vms_on_labeled_node, node_before=node_with_least_available_memory
            )
