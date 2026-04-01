# -*- coding: utf-8 -*-

"""
Utility functions and constants for CDI Config tests
"""

from ocp_resources.cdi import CDI

from tests.storage.utils import import_image_to_dv, upload_image_to_dv, upload_token_request
from utilities.constants import Images
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import (
    check_disk_count_in_vm,
    create_vm_from_dv,
    get_downloaded_artifact,
    wait_for_default_sc_in_cdiconfig,
)

STORAGE_WORKLOADS_DICT = {
    "limits": {"cpu": "505m", "memory": "2Gi"},
    "requests": {"cpu": "252m", "memory": "1Gi"},
}
NON_EXISTENT_SCRATCH_SC_DICT = {"scratchSpaceStorageClass": "NonExistentSC"}
INSECURE_REGISTRIES_LIST = ["added-private-registry:5000"]


def cdiconfig_update(
    source,
    hco_cr,
    cdiconfig,
    storage_class_type,
    storage_ns_name,
    dv_name,
    client,
    https_server_certificate,
    images_https_server_name="",
    run_vm=False,
    tmpdir=None,
):
    def _create_vm_check_disk_count(dv):
        dv.wait_for_dv_success()
        with create_vm_from_dv(dv=dv, client=client) as vm_dv:
            check_disk_count_in_vm(vm=vm_dv)

    with ResourceEditorValidateHCOReconcile(
        patches={hco_cr: {"spec": {"scratchSpaceStorageClass": storage_class_type}}},
        list_resource_reconcile=[CDI],
    ):
        wait_for_default_sc_in_cdiconfig(cdi_config=cdiconfig, sc=storage_class_type)

        if run_vm:
            if source == "http":
                with import_image_to_dv(
                    dv_name=dv_name,
                    images_https_server_name=images_https_server_name,
                    storage_ns_name=storage_ns_name,
                    https_server_certificate=https_server_certificate,
                    client=client,
                ) as dv:
                    _create_vm_check_disk_count(dv=dv)
            elif source == "upload":
                local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
                remote_name = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
                get_downloaded_artifact(remote_name=remote_name, local_name=local_name)
                with upload_image_to_dv(
                    dv_name=dv_name,
                    storage_ns_name=storage_ns_name,
                    storage_class=storage_class_type,
                    client=client,
                ) as dv:
                    upload_token_request(storage_ns_name, pvc_name=dv.pvc.name, data=local_name, client=client)
                    _create_vm_check_disk_count(dv=dv)
