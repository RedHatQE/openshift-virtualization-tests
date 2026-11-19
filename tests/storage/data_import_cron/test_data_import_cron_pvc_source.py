import logging

LOGGER = logging.getLogger(__name__)


class TestDataImportCronPvcSource:
    def test_data_import_cron_with_pvc_source_ready(
        self, namespace, dv_source_for_data_import_cron, data_import_cron_with_pvc_source, imported_data_source
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-54821 # <skip-jira-utils-check>
        Polarion: CNV-11842
        """
        imported_data_source.wait_for_condition(
            condition=imported_data_source.Condition.READY, status=imported_data_source.Condition.Status.TRUE
        )

    def test_data_import_cron_vm_from_import_pvc(
        self, namespace, data_import_cron_with_pvc_source, vm_for_data_source_import
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-54821 # <skip-jira-utils-check>
        Polarion: CNV-11858
        """
        assert vm_for_data_source_import, f"vm {vm_for_data_source_import} did not created from the imported source pvc"
