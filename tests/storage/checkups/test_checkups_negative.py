import pytest
from ocp_resources.job import Job

from tests.storage.checkups.utils import assert_results_in_configmap

DEFAULT_STORAGE_CLASS_ENTRY = "defaultStorageClass"
MSG_NO_DEFAULT_STORAGE_CLASS = "no default storage class"
MSG_NOT_READY_DATA_SOURCES = "there are golden images whose DataImportCron is not up to date or DataSource is not ready"
MSG_MULTIPLE_DEFAULT_SC = "there are multiple default storage classes"
MSG_UNKNOWN_PROVISIONER = "there are StorageProfiles with empty ClaimPropertySets"


@pytest.mark.parametrize(
    "checkup_job",
    [
        pytest.param(
            {"expected_condition": Job.Status.FAILED},
        ),
    ],
    indirect=True,
)
class TestCheckupNegative:
    @pytest.mark.polarion("CNV-10701")
    def test_no_default_storage_class(
        self,
        removed_default_storage_classes,
        rhel9_data_import_cron_source_format,
        checkup_configmap,
        checkup_job,
    ):
        """
        Checkup Should Fail when there is no default StorageClass
        """
        assert_results_in_configmap(
            configmap=checkup_configmap,
            expected_failure_msg=MSG_NO_DEFAULT_STORAGE_CLASS,
            expected_result=MSG_NO_DEFAULT_STORAGE_CLASS,
            result_entry=DEFAULT_STORAGE_CLASS_ENTRY,
        )

    @pytest.mark.polarion("CNV-10705")
    def test_additional_default_storage_class(
        self,
        updated_two_default_storage_classes,
        rhel9_data_import_cron_source_format,
        checkup_configmap,
        checkup_job,
    ):
        """
        Checkup should fail when there is more than one default StorageClass
        """
        assert_results_in_configmap(
            configmap=checkup_configmap,
            expected_failure_msg=MSG_MULTIPLE_DEFAULT_SC,
            expected_result=MSG_MULTIPLE_DEFAULT_SC,
            result_entry=DEFAULT_STORAGE_CLASS_ENTRY,
        )

    @pytest.mark.polarion("CNV-10706")
    def test_unknown_provisioner(
        self,
        storage_class_with_unknown_provisioner,
        checkup_configmap,
        checkup_job,
    ):
        """
        Checkup should fail when there is StorageClass with unknown provisioner.
        """
        assert_results_in_configmap(
            configmap=checkup_configmap,
            expected_failure_msg=MSG_UNKNOWN_PROVISIONER,
            expected_result=storage_class_with_unknown_provisioner.name,
            result_entry="storageProfilesWithEmptyClaimPropertySets",
        )

    @pytest.mark.polarion("CNV-10711")
    def test_golden_image_data_source_not_ready(
        self,
        broken_data_import_cron,
        checkup_configmap,
        checkup_job,
    ):
        """
        Checkup should fail when there are golden image DataSources not ready
        """
        assert_results_in_configmap(
            configmap=checkup_configmap,
            expected_failure_msg=MSG_NOT_READY_DATA_SOURCES,
            expected_result=broken_data_import_cron.name,
            result_entry="goldenImagesNotUpToDate",
        )
