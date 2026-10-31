"""
Upload tests
"""

import logging
import time
from random import shuffle

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.route import Route
from ocp_resources.upload_token_request import UploadTokenRequest
from pytest_testconfig import config as py_config

import tests.storage.utils as storage_utils
from tests.os_params import RHEL_LATEST
from tests.storage.cdi_upload.utils import upload_images_to_multiple_dvs, wait_for_upload_response_code
from tests.storage.stop_status_utils import dv_stop_status_restart_threshold
from utilities.constants import Images
from utilities.constants.components import CDI_UPLOADPROXY
from utilities.constants.timeouts import TIMEOUT_3MIN
from utilities.storage import create_vm_from_dv, get_downloaded_artifact

LOGGER = logging.getLogger(__name__)
HTTP_UNAUTHORIZED = 401
HTTP_OK = 200
# Fixed count to ensure consistent test behavior and reliability
CONCURRENT_UPLOAD_DVS_COUNT = 10


@pytest.mark.polarion("CNV-2318")
@pytest.mark.s390x
def test_cdi_uploadproxy_route_owner_references(admin_client, hco_namespace):
    route = Route(name=CDI_UPLOADPROXY, namespace=hco_namespace.name, client=admin_client)
    assert route.instance
    assert route.instance["metadata"]["ownerReferences"][0]["name"] == "cdi-deployment"
    assert route.instance["metadata"]["ownerReferences"][0]["kind"] == "Deployment"


@pytest.mark.sno
@pytest.mark.parametrize(
    ("dv_name", "remote_name", "local_name"),
    [
        pytest.param(
            "cnv-875",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
            Images.Cirros.QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-875"), pytest.mark.sno()),
            id=f"cnv-875-{Images.Cirros.QCOW2_IMG}",
        ),
        pytest.param(
            "cnv-2007",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG_GZ}",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-2007"), pytest.mark.post_upgrade()),
            id=f"cnv-2007-{Images.Cirros.QCOW2_IMG_GZ}",
        ),
        pytest.param(
            "cnv-8908",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG_XZ}",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-8908")),
            id=f"cnv-8908-{Images.Cirros.QCOW2_IMG_XZ}",
        ),
        pytest.param(
            "cnv-8909",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.RAW_IMG,
            marks=(pytest.mark.polarion("CNV-8909")),
            id=f"cnv-8909-{Images.Cirros.RAW_IMG}",
        ),
        pytest.param(
            "cnv-8910",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_GZ}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-8910")),
            id=f"cnv-8910-{Images.Cirros.RAW_IMG_GZ}",
        ),
        pytest.param(
            "cnv-8911",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_XZ}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-8911")),
            id=f"cnv-8911-{Images.Cirros.RAW_IMG_XZ}",
        ),
        pytest.param(
            "cnv-2008",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.QCOW2_IMG,
            marks=(pytest.mark.polarion("CNV-2008")),
            id=f"cnv-2008-{Images.Cirros.RAW_IMG}-saved-as-{Images.Cirros.QCOW2_IMG}",
        ),
        pytest.param(
            "cnv-8912",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
            Images.Cirros.QCOW2_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-8912")),
            id=f"cnv-8912-{Images.Cirros.QCOW2_IMG}-saved-as-{Images.Cirros.QCOW2_IMG_XZ}",
        ),
        pytest.param(
            "cnv-8913",
            f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
            Images.Cirros.QCOW2_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-8913")),
            id=f"cnv-8913-{Images.Cirros.QCOW2_IMG}-saved-as-{Images.Cirros.QCOW2_IMG_GZ}",
        ),
        pytest.param(
            "cnv-8914",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-8914")),
            id=f"cnv-8914-{Images.Cirros.RAW_IMG}-saved-as-{Images.Cirros.RAW_IMG_XZ}",
        ),
        pytest.param(
            "cnv-8915",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-8915")),
            id=f"cnv-8915-{Images.Cirros.RAW_IMG}-saved-as-{Images.Cirros.RAW_IMG_GZ}",
        ),
        pytest.param(
            "cnv-8916",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_GZ}",
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-8916")),
            id=f"cnv-8916-{Images.Cirros.RAW_IMG_GZ}-saved-as-{Images.Cirros.RAW_IMG_XZ}",
        ),
        pytest.param(
            "cnv-8917",
            f"{Images.Cirros.DIR}/{Images.Cirros.RAW_IMG_XZ}",
            Images.Cirros.RAW_IMG_GZ,
            marks=(pytest.mark.polarion("CNV-8917")),
            id=f"cnv-8917-{Images.Cirros.RAW_IMG_XZ}-saved-as-{Images.Cirros.RAW_IMG_GZ}",
        ),
    ],
)
def test_successful_upload_with_supported_formats(
    unprivileged_client,
    namespace,
    tmpdir,
    dv_name,
    remote_name,
    local_name,
):
    local_name = f"{tmpdir}/{local_name}"
    get_downloaded_artifact(remote_name=remote_name, local_name=local_name)
    with storage_utils.upload_image_to_dv(
        dv_name=dv_name,
        storage_class=py_config["default_storage_class"],
        storage_ns_name=namespace.name,
        client=unprivileged_client,
    ) as dv:
        storage_utils.upload_token_request(
            storage_ns_name=namespace.name, pvc_name=dv.pvc.name, data=local_name, client=unprivileged_client
        )
        dv.wait_for_dv_success(stop_status_func=dv_stop_status_restart_threshold, dv=dv)
        create_vm_from_dv(client=unprivileged_client, dv=dv)


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-2018",
                "source": "upload",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
                "wait": False,
            },
            marks=(pytest.mark.polarion("CNV-2018")),
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.polarion("CNV-2018")
@pytest.mark.s390x
def test_successful_upload_token_validity(
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    upload_file_path,
):
    dv = data_volume_multi_storage_scope_function
    dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_3MIN)
    with UploadTokenRequest(
        client=unprivileged_client,
        name=dv.name,
        namespace=namespace.name,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        wait_for_upload_response_code(token=shuffle(list(token)), data="test", response_code=HTTP_UNAUTHORIZED)
    with UploadTokenRequest(
        client=unprivileged_client,
        name=dv.name,
        namespace=namespace.name,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        wait_for_upload_response_code(token=token, data=upload_file_path, response_code=HTTP_OK)
        dv.wait_for_dv_success(stop_status_func=dv_stop_status_restart_threshold, dv=dv)


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-2011",
                "source": "upload",
                "dv_size": "3Gi",
                "wait": False,
            },
            marks=(pytest.mark.polarion("CNV-2011")),
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.polarion("CNV-2011")
@pytest.mark.s390x
def test_successful_upload_token_expiry(unprivileged_client, namespace, data_volume_multi_storage_scope_function):
    dv = data_volume_multi_storage_scope_function
    dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_3MIN)
    with UploadTokenRequest(
        client=unprivileged_client,
        name=dv.name,
        namespace=namespace.name,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        LOGGER.info("Wait until token expires ...")
        time.sleep(310)
        wait_for_upload_response_code(token=token, data="test", response_code=HTTP_UNAUTHORIZED)


@pytest.mark.sno
@pytest.mark.s390x
@pytest.mark.polarion("CNV-2015")
@pytest.mark.parametrize(
    "upload_file_path",
    [
        pytest.param(
            {
                "remote_image_dir": Images.Alpine.DIR,
                "remote_image_name": Images.Alpine.QCOW2_IMG,
            },
        ),
    ],
    indirect=True,
)
def test_successful_concurrent_uploads(
    admin_client,
    upload_file_path,
    namespace,
    storage_class_matrix__module__,
):
    """Test concurrent uploads to multiple DataVolumes.

    Preconditions:
        - Storage class supporting dynamic provisioning

    Steps:
        1. Create 10 DataVolumes with "upload" source
        2. Wait for UPLOAD_READY status on all DataVolumes
        3. Upload images to all DataVolumes concurrently

    Expected:
        - All uploads complete successfully with HTTP 200
    """

    upload_images_to_multiple_dvs(
        client=admin_client,
        namespace_name=namespace.name,
        storage_class=[*storage_class_matrix__module__][0],
        num_dvs=CONCURRENT_UPLOAD_DVS_COUNT,
        upload_file_path=upload_file_path,
    )


@pytest.mark.sno
@pytest.mark.parametrize(
    "download_specified_image, data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "image_path": RHEL_LATEST.get("image_path"),
                "image_file": RHEL_LATEST.get("image_name"),
            },
            {
                "dv_name": "cnv-4511",
                "source": "upload",
                "dv_size": "3Gi",
                "wait": True,
            },
            marks=(pytest.mark.polarion("CNV-4511")),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_print_response_body_on_error_upload(
    unprivileged_client,
    namespace,
    download_specified_image,
    data_volume_multi_storage_scope_function,
):
    """
    Check that CDI now reports validation failures as part of the body response
    in case for instance the disk image virtual size > PVC size > disk size
    """
    dv = data_volume_multi_storage_scope_function
    with UploadTokenRequest(
        client=unprivileged_client,
        name=dv.name,
        namespace=dv.namespace,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        LOGGER.debug("Start upload an image asynchronously ...")

        # Upload should fail with an error
        wait_for_upload_response_code(
            token=token,
            data=download_specified_image,
            response_code=400,
            asynchronous=True,
        )
