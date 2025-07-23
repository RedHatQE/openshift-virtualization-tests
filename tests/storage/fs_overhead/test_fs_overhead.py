"""
Filesystem overhead test suite
"""

import bitmath
import pytest
from ocp_resources.cdi import CDI
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

from tests.utils import create_cirros_vm
from utilities.constants import Images
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import virtctl_upload_dv

FS_OVERHEAD_20 = 0.2


def get_pvc_size_gib(pvc):
    return bitmath.Byte(int(pvc.instance.spec.resources.requests.storage)).to_GiB()


def assert_fs_overhead_added(actual_size, requested_size):
    expected_size = actual_size * (1 - FS_OVERHEAD_20)
    assert expected_size == requested_size, (
        f"actual size: {actual_size}, expected size: {expected_size}, requested size: {requested_size}"
    )


@pytest.fixture(scope="module")
def updated_fs_overhead_20_with_hco(storage_class_with_filesystem_volume_mode, hyperconverged_resource_scope_module):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: {
                "spec": {
                    "filesystemOverhead": {
                        "storageClass": {storage_class_with_filesystem_volume_mode: str(FS_OVERHEAD_20)}
                    }
                }
            }
        },
        list_resource_reconcile=[CDI],
        wait_for_reconcile_post_update=True,
    ) as edited_cdi_config:
        yield edited_cdi_config


@pytest.fixture()
def vm_for_fs_overhead_test(namespace, unprivileged_client, storage_class_with_filesystem_volume_mode):
    with create_cirros_vm(
        storage_class=storage_class_with_filesystem_volume_mode,
        namespace=namespace.name,
        client=unprivileged_client,
        dv_name="fs-overhead-dv",
        vm_name="fs-overhead-vm",
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as vm:
        yield vm


@pytest.fixture()
def uploaded_cirros_dv(
    namespace,
    downloaded_cirros_image_full_path,
    downloaded_cirros_image_scope_class,
    storage_class_with_filesystem_volume_mode,
):
    dv_name = "uploaded-dv"
    with virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size=Images.Cirros.DEFAULT_DV_SIZE,
        image_path=downloaded_cirros_image_full_path,
        storage_class=storage_class_with_filesystem_volume_mode,
        volume_mode=DataVolume.VolumeMode.FILE,
        insecure=True,
    ):
        yield DataVolume(name=dv_name, namespace=namespace.name)


@pytest.mark.polarion("CNV-8635")
def test_import_vm_with_specify_fs_overhead(updated_fs_overhead_20_with_hco, vm_for_fs_overhead_test):
    vm_metadata = vm_for_fs_overhead_test.data_volume_template["metadata"]
    assert_fs_overhead_added(
        actual_size=get_pvc_size_gib(
            pvc=PersistentVolumeClaim(name=vm_metadata["name"], namespace=vm_metadata["namespace"])
        ),
        requested_size=bitmath.GiB(
            int(vm_for_fs_overhead_test.data_volume_template["spec"]["storage"]["resources"]["requests"]["storage"][0])
        ),
    )


@pytest.mark.polarion("CNV-8637")
def test_upload_dv_with_specify_fs_overhead(
    updated_fs_overhead_20_with_hco,
    uploaded_cirros_dv,
):
    assert_fs_overhead_added(
        actual_size=get_pvc_size_gib(pvc=uploaded_cirros_dv.pvc),
        requested_size=bitmath.GiB(int(Images.Cirros.DEFAULT_DV_SIZE[0])),
    )
