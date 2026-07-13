"""
Cross-cluster live migration tests.

Jira: https://redhat.atlassian.net/browse/CNV-50823 # <skip-jira-utils-check>
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytest_testconfig import config as py_config

from tests.storage.constants import STORAGE_CLASS_A, STORAGE_CLASS_B, TEST_FILE_CONTENT, TEST_FILE_NAME
from tests.storage.cross_cluster_live_migration.utils import (
    assert_vms_are_stopped,
    assert_vms_can_be_deleted,
    verify_compute_live_migration_after_cclm,
    verify_vms_boot_id_after_cross_cluster_live_migration,
    wait_for_vms_to_be_stopped,
)
from tests.storage.utils import check_file_in_vm
from utilities.constants import TIMEOUT_10MIN, TIMEOUT_50MIN

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests

TESTS_CLASS_NAME_SEVERAL_VMS = "TestCCLMSeveralVMs"
TESTS_CLASS_NAME_WINDOWS_VM = "TestCCLMWindowsWithVTPM"
TESTS_CLASS_NAME_STORAGE_A_TO_B = "TestCCLMFromStorageAtoB"

pytestmark = [
    pytest.mark.cclm,
    pytest.mark.remote_cluster,
    pytest.mark.usefixtures(
        "remote_cluster_configured_hco_live_migration_network",
        "local_cluster_configured_hco_live_migration_network",
    ),
]


@pytest.mark.parametrize(
    "remote_cluster_source_storage_class, local_cluster_target_storage_class, vms_for_cclm",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_B]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            {
                "vms_fixtures": [
                    "vm_for_cclm_from_template_with_data_source",
                    "vm_for_cclm_with_instance_type",
                ]
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("remote_cluster_source_storage_class", "local_cluster_target_storage_class")
class TestCCLMSeveralVMs:
    """
    Tests for cross-cluster live migration of multiple VMs.

    Preconditions:
        - Two OpenShift clusters (source and target) with live migration network configured
        - MTV installed on the target cluster with Provider, StorageMap, and NetworkMap configured
        - Several running VMs on the source cluster, accessible via console
        - Test file written to the source VMs before migration
        - Boot IDs recorded for all source VMs before migration
    """

    @pytest.mark.polarion("CNV-11995")
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME_SEVERAL_VMS}::test_migrate_vm_from_remote_to_local_cluster")
    def test_migrate_vm_from_remote_to_local_cluster(
        self,
        written_file_to_vms_before_cclm,
        vms_boot_id_before_cclm,
        mtv_migration,
    ):
        """
        Test that multiple VMs can be live migrated from the source cluster to the target cluster.

        Steps:
            1. Wait for the MTV migration to reach Succeeded condition

        Expected:
            - Migration succeeds for all VMs
        """
        mtv_migration.wait_for_condition(
            condition=mtv_migration.Condition.Type.SUCCEEDED,
            status=mtv_migration.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
            stop_condition=mtv_migration.Status.FAILED,
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME_SEVERAL_VMS}::test_migrate_vm_from_remote_to_local_cluster"])
    @pytest.mark.polarion("CNV-11910")
    def test_verify_vms_not_rebooted_after_migration(self, local_vms_after_cclm_migration, vms_boot_id_before_cclm):
        """
        Test that VMs are not rebooted during cross-cluster live migration.

        Preconditions:
            - Source VMs successfully migrated to the target cluster

        Steps:
            1. Read boot ID from each migrated VM on the target cluster
            2. Compare current boot IDs with boot IDs recorded before migration

        Expected:
            - Boot IDs are unchanged for all migrated VMs
        """
        verify_vms_boot_id_after_cross_cluster_live_migration(
            local_vms=local_vms_after_cclm_migration, initial_boot_id=vms_boot_id_before_cclm
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME_SEVERAL_VMS}::test_migrate_vm_from_remote_to_local_cluster"])
    @pytest.mark.polarion("CNV-14332")
    def test_verify_file_persisted_after_migration(self, local_vms_after_cclm_migration):
        """
        Test that files written before migration are preserved after cross-cluster live migration.

        Preconditions:
            - Source VMs successfully migrated to the target cluster

        Steps:
            1. Read the test file from each migrated VM on the target cluster

        Expected:
            - File content on each migrated VM equals the content written before migration
        """
        for vm in local_vms_after_cclm_migration:
            check_file_in_vm(
                vm=vm,
                file_name=TEST_FILE_NAME,
                file_content=TEST_FILE_CONTENT,
                username=vm.username,
                password=vm.password,
            )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME_SEVERAL_VMS}::test_migrate_vm_from_remote_to_local_cluster"])
    @pytest.mark.polarion("CNV-14333")
    def test_source_vms_are_stopped_after_cclm(self, vms_for_cclm):
        """
        Test that source VMs on the source cluster are stopped after cross-cluster live migration.

        Preconditions:
            - Source VMs successfully migrated to the target cluster

        Steps:
            1. Check the status of each source VM on the source cluster

        Expected:
            - All source VMs are in "Stopped" state
        """
        assert_vms_are_stopped(vms=vms_for_cclm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME_SEVERAL_VMS}::test_migrate_vm_from_remote_to_local_cluster"])
    @pytest.mark.polarion("CNV-12038")
    def test_compute_live_migrate_vms_after_cclm(
        self, admin_client: DynamicClient, local_vms_after_cclm_migration: list[VirtualMachineForTests]
    ):
        """
        Test that VMs can be compute live migrated within the target cluster after cross-cluster live migration.

        Preconditions:
            - Source VMs successfully migrated to the target cluster

        Steps:
            1. Trigger intra-cluster live migration for each migrated VM on the target cluster
            2. Wait for each migration to complete

        Expected:
            - All migrated VMs are successfully live migrated within the target cluster
        """
        verify_compute_live_migration_after_cclm(client=admin_client, local_vms=local_vms_after_cclm_migration)

    @pytest.mark.polarion("CNV-14334")
    def test_source_vms_can_be_deleted(self, vms_for_cclm):
        """
        Test that source VMs on the source cluster can be deleted after cross-cluster live migration.

        Steps:
            1. Delete each source VM on the source cluster

        Expected:
            - All source VMs are successfully deleted
        """
        assert_vms_can_be_deleted(vms=vms_for_cclm)

    @pytest.mark.polarion("CNV-15237")
    def test_target_vms_can_be_deleted(self, local_vms_after_cclm_migration):
        """
        Test that migrated VMs on the target cluster can be deleted after cross-cluster live migration.

        Steps:
            1. Delete each migrated VM on the target cluster

        Expected:
            - All migrated VMs are successfully deleted
        """
        assert_vms_can_be_deleted(vms=local_vms_after_cclm_migration)


@pytest.mark.parametrize(
    "remote_cluster_source_storage_class, local_cluster_target_storage_class, dv_wait_timeout, vms_for_cclm",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_B]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            {"dv_wait_timeout": TIMEOUT_50MIN},
            {"vms_fixtures": ["vm_for_cclm_windows_with_instance_type"]},
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("remote_cluster_source_storage_class", "local_cluster_target_storage_class", "dv_wait_timeout")
class TestCCLMWindowsWithVTPM:
    """
    Tests for cross-cluster live migration of a Windows VM with vTPM.

    Preconditions:
        - Two OpenShift clusters (source and target) with live migration network configured
        - MTV installed on the target cluster with Provider, StorageMap, and NetworkMap configured
        - Running Windows VM on the source cluster
    """

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME_WINDOWS_VM}::test_migrate_windows_vm_from_remote_to_local_cluster")
    @pytest.mark.polarion("CNV-11999")
    def test_migrate_windows_vm_from_remote_to_local_cluster(
        self,
        booted_vms_for_cclm,
        mtv_migration,
    ):
        """
        Test that a Windows VM can be live migrated from the source cluster to the target cluster.

        Steps:
            1. Wait for the MTV migration to reach Succeeded condition

        Expected:
            - Migration succeeds for the Windows VM
        """
        mtv_migration.wait_for_condition(
            condition=mtv_migration.Condition.Type.SUCCEEDED,
            status=mtv_migration.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
            stop_condition=mtv_migration.Status.FAILED,
        )

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_WINDOWS_VM}::test_migrate_windows_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-14335")
    def test_source_vms_are_stopped_after_cclm(self, vms_for_cclm):
        """
        Test that the source Windows VM on the source cluster is stopped after cross-cluster live migration.

        Preconditions:
            - Source VM successfully migrated to the target cluster

        Steps:
            1. Wait for the source VM on the source cluster to reach Stopped state

        Expected:
            - Source VM is in "Stopped" state
        """
        wait_for_vms_to_be_stopped(vms=vms_for_cclm)

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_WINDOWS_VM}::test_migrate_windows_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-12474")
    def test_compute_live_migrate_windows_vms_after_cclm(
        self, admin_client: DynamicClient, local_vms_after_cclm_migration: list[VirtualMachineForTests]
    ):
        """
        Test that a Windows VM can be compute live migrated within the target cluster after cross-cluster live migration.

        Preconditions:
            - Source VM successfully migrated to the target cluster

        Steps:
            1. Trigger intra-cluster live migration for the migrated Windows VM on the target cluster
            2. Wait for migration to complete

        Expected:
            - Migrated Windows VM is successfully live migrated within the target cluster
        """
        verify_compute_live_migration_after_cclm(client=admin_client, local_vms=local_vms_after_cclm_migration)

    @pytest.mark.polarion("CNV-14336")
    def test_source_vms_can_be_deleted(self, vms_for_cclm):
        """
        Test that the source Windows VM on the source cluster can be deleted after cross-cluster live migration.

        Steps:
            1. Delete the source VM on the source cluster

        Expected:
            - Source VM is successfully deleted
        """
        assert_vms_can_be_deleted(vms=vms_for_cclm)

    @pytest.mark.polarion("CNV-15236")
    def test_target_vms_can_be_deleted(self, local_vms_after_cclm_migration):
        """
        Test that the migrated Windows VM on the target cluster can be deleted after cross-cluster live migration.

        Steps:
            1. Delete the migrated VM on the target cluster

        Expected:
            - Migrated VM is successfully deleted
        """
        assert_vms_can_be_deleted(vms=local_vms_after_cclm_migration)


@pytest.mark.parametrize(
    "remote_cluster_source_storage_class, local_cluster_target_storage_class, vms_for_cclm",
    [
        pytest.param(
            {"source_storage_class": py_config[STORAGE_CLASS_A]},
            {"target_storage_class": py_config[STORAGE_CLASS_B]},
            {
                "vms_fixtures": [
                    "vm_for_cclm_with_instance_type",
                ]
            },
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("remote_cluster_source_storage_class", "local_cluster_target_storage_class")
class TestCCLMFromStorageAtoB:
    """
    Tests for cross-cluster live migration of a VM across different storage classes.

    Preconditions:
        - Two OpenShift clusters (source and target) with live migration network configured
        - MTV installed on the target cluster with Provider, StorageMap, and NetworkMap configured
        - Running VM on the source cluster, accessible via console
        - Different storage classes used on source and target clusters
        - Test file written to the source VM before migration
        - Boot ID recorded for the source VM before migration
    """

    @pytest.mark.polarion("CNV-15955")
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME_STORAGE_A_TO_B}::test_migrate_vm_from_remote_to_local_cluster")
    def test_migrate_vm_from_remote_to_local_cluster(
        self,
        written_file_to_vms_before_cclm,
        vms_boot_id_before_cclm,
        mtv_migration,
    ):
        """
        Test that a VM can be cross-cluster live migrated when source and target storage classes are different.

        Steps:
            1. Wait for the MTV migration to reach Succeeded condition

        Expected:
            - Migration succeeds for the VM
        """
        mtv_migration.wait_for_condition(
            condition=mtv_migration.Condition.Type.SUCCEEDED,
            status=mtv_migration.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
            stop_condition=mtv_migration.Status.FAILED,
        )

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_STORAGE_A_TO_B}::test_migrate_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-15956")
    def test_verify_vms_not_rebooted_after_migration(self, local_vms_after_cclm_migration, vms_boot_id_before_cclm):
        """
        Test that VM is not rebooted during cross-cluster live migration.

        Preconditions:
            - Source VM successfully migrated to the target cluster

        Steps:
            1. Read boot ID from the migrated VM on the target cluster
            2. Compare current boot ID with boot ID recorded before migration

        Expected:
            - Boot ID is unchanged for the migrated VM
        """
        verify_vms_boot_id_after_cross_cluster_live_migration(
            local_vms=local_vms_after_cclm_migration, initial_boot_id=vms_boot_id_before_cclm
        )

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_STORAGE_A_TO_B}::test_migrate_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-15957")
    def test_verify_file_persisted_after_migration(self, local_vms_after_cclm_migration):
        """
        Test that files written before migration are preserved after cross-cluster live migration.

        Preconditions:
            - Source VM successfully migrated to the target cluster

        Steps:
            1. Read the test file from the migrated VM on the target cluster

        Expected:
            - File content on the migrated VM equals the content written before migration
        """
        for vm in local_vms_after_cclm_migration:
            check_file_in_vm(
                vm=vm,
                file_name=TEST_FILE_NAME,
                file_content=TEST_FILE_CONTENT,
                username=vm.username,
                password=vm.password,
            )

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_STORAGE_A_TO_B}::test_migrate_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-15958")
    def test_source_vms_are_stopped_after_cclm(self, vms_for_cclm):
        """
        Test that source VM on the source cluster is stopped after cross-cluster live migration.

        Preconditions:
            - Source VM successfully migrated to the target cluster

        Steps:
            1. Check the status of the source VM on the source cluster

        Expected:
            - Source VM is in "Stopped" state
        """
        assert_vms_are_stopped(vms=vms_for_cclm)

    @pytest.mark.dependency(
        depends=[f"{TESTS_CLASS_NAME_STORAGE_A_TO_B}::test_migrate_vm_from_remote_to_local_cluster"]
    )
    @pytest.mark.polarion("CNV-15954")
    def test_compute_live_migrate_vms_after_cclm(
        self, admin_client: DynamicClient, local_vms_after_cclm_migration: list[VirtualMachineForTests]
    ):
        """
        Test that a VM can be compute live migrated within the target cluster after cross-cluster live migration.

        Preconditions:
            - Source VM successfully migrated to the target cluster

        Steps:
            1. Trigger intra-cluster live migration for the migrated VM on the target cluster
            2. Wait for migration to complete

        Expected:
            - Migrated VM is successfully live migrated within the target cluster
        """
        verify_compute_live_migration_after_cclm(client=admin_client, local_vms=local_vms_after_cclm_migration)

    @pytest.mark.polarion("CNV-15959")
    def test_source_vms_can_be_deleted(self, vms_for_cclm):
        """
        Test that source VM on the source cluster can be deleted after cross-cluster live migration.

        Steps:
            1. Delete the source VM on the source cluster

        Expected:
            - Source VM is successfully deleted
        """
        assert_vms_can_be_deleted(vms=vms_for_cclm)

    @pytest.mark.polarion("CNV-15960")
    def test_target_vms_can_be_deleted(self, local_vms_after_cclm_migration):
        """
        Test that migrated VM on the target cluster can be deleted after cross-cluster live migration.

        Steps:
            1. Delete the migrated VM on the target cluster

        Expected:
            - Migrated VM is successfully deleted
        """
        assert_vms_can_be_deleted(vms=local_vms_after_cclm_migration)
