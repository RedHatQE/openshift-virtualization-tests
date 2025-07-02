import logging

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.job import Job

from tests.storage.checkups.utils import assert_results_in_configmap

MSG_MIGRATION_FAIL = "cannot migrate VMI"
MSG_MIGRATION_SUCCESS = "migration completed"

LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "checkup_job",
    [
        pytest.param(
            {
                "expected_condition": Job.Condition.COMPLETE,
            },
        ),
    ],
    indirect=True,
)
class TestCheckupPositive:
    @pytest.mark.polarion("CNV-10707")
    @pytest.mark.s390x
    def test_overriden_storage_profile_claim_propertyset(
        self,
        updated_default_storage_profile,
        checkup_configmap,
        checkup_job,
    ):
        """
        Checkup should succeed and mention in result configmap if a StorageProfile ClaimPropertySet overriden
        """
        assert_results_in_configmap(
            configmap=checkup_configmap,
            expected_result=updated_default_storage_profile.name,
            result_entry="storageProfilesWithSpecClaimPropertySets",
        )

    @pytest.mark.polarion("CNV-10708")
    @pytest.mark.s390x
    def test_storage_profile_missing_volume_snapshot_class(
        self,
        updated_storage_class_snapshot_clone_strategy,
        checkup_configmap,
        checkup_job,
    ):
        """
        Checkup should succeed and mention in result configmap if there is SC with "snapshot" clone strategy
         without VolumeSnapshotClass
        """
        assert_results_in_configmap(
            configmap=checkup_configmap,
            expected_result=updated_storage_class_snapshot_clone_strategy.name,
            result_entry="storageProfileMissingVolumeSnapshotClass",
        )

    @pytest.mark.polarion("CNV-10709")
    @pytest.mark.s390x
    def test_ocs_rbd_non_virt_vm_exist(
        self,
        skip_if_no_ocs_rbd_non_virt_sc,
        ocs_rbd_non_virt_vm_for_checkups_test,
        checkup_configmap,
        checkup_job,
    ):
        """
        Checkup should succeed but mention in comfigmap if a VM with non-virt rbd StorageClass exists
        """
        assert_results_in_configmap(
            configmap=checkup_configmap,
            expected_result=ocs_rbd_non_virt_vm_for_checkups_test.name,
            result_entry="vmsWithNonVirtRbdStorageClass",
        )

    @pytest.mark.polarion("CNV-10712")
    @pytest.mark.s390x
    def test_checkup_live_migration(
        self,
        default_storage_class_access_modes,
        checkup_configmap,
        checkup_job,
    ):
        """
        checkup should succeed, and the migration should succeed if and only if the default StorageClass accessMode
        is RWX
        """
        expected_result = (
            MSG_MIGRATION_SUCCESS
            if DataVolume.AccessMode.RWX in default_storage_class_access_modes
            else MSG_MIGRATION_FAIL
        )

        assert_results_in_configmap(
            configmap=checkup_configmap,
            expected_result=expected_result,
            result_entry="vmLiveMigration",
        )
