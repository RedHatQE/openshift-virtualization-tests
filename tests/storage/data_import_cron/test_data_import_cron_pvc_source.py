import logging

import pytest

LOGGER = logging.getLogger(__name__)


class TestDataImportCronPvcSource:
    @pytest.mark.polarion("CNV-11842")
    def test_data_import_cron_with_pvc_source_ready(
        self, namespace, dv_vm_for_data_import_cron, data_import_cron_pvc_source
    ):
        pvc_uid = dv_vm_for_data_import_cron.pvc.instance.metadata.uid

        digest_full = data_import_cron_pvc_source.instance.status.currentImports[0].Digest
        digest_uid = digest_full.split("uid:")[1]  # Extract just the UUID part
        assert pvc_uid == digest_uid, f"PVC UID {pvc_uid} does not match DataImportCron Digest {digest_uid}"
