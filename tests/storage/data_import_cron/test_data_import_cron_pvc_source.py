import logging

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

from utilities.constants import TIMEOUT_5MIN

LOGGER = logging.getLogger(__name__)


class TestDataImportCronPvcSource:
    @pytest.mark.polarion("CNV-11842")
    def test_data_import_cron_with_pvc_source_ready(
        self, namespace, dv_source_for_data_import_cron, data_import_cron_with_pvc_source
    ):
        data_import_cron_with_pvc_source.wait_for_condition(
            condition="UpToDate", status=data_import_cron_with_pvc_source.Condition.Status.TRUE
        )
        dv_source_for_data_import_cron.pvc.wait_for_status(
            status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_5MIN
        )

    @pytest.mark.polarion("CNV-11858")
    def test_data_import_cron_vm_from_import_pvc(self, namespace, vm_for_dv_target):
        assert vm_for_dv_target, f"vm {vm_for_dv_target} did not created from the imported source pvc "

    @pytest.mark.polarion("CNV-11884")
    def test_source_pvc_data_import_cron_re_import(
        self,
        namespace,
        unprivileged_client,
        data_import_cron_pvc_target_namespace,
        recreate_dv_source_for_data_import_cron,
        data_import_cron_with_pvc_source,
    ):
        data_import_cron_with_pvc_source.wait_for_condition(
            condition="UpToDate", status=data_import_cron_with_pvc_source.Condition.Status.TRUE
        )

        list_pvc_target_namespace = list(
            DataVolume.get(dyn_client=unprivileged_client, namespace=data_import_cron_pvc_target_namespace.name)
        )
        assert len(list_pvc_target_namespace), (
            f"expected number of PVC's in namespace :{data_import_cron_pvc_target_namespace.name} is 2"
            f"current PVC's:  {list_pvc_target_namespace}"
        )

        for target_pvc in list_pvc_target_namespace:
            target_pvc.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_5MIN)
