# -*- coding: utf-8 -*-

"""
Upload tests
"""

import logging
import multiprocessing
import time
from time import sleep

import pytest
import sh
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume import PersistentVolume
from ocp_resources.route import Route
from ocp_resources.upload_token_request import UploadTokenRequest
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutSampler

import tests.storage.utils as storage_utils
import utilities.storage
from tests.os_params import RHEL_LATEST
from utilities.constants import (
    CDI_UPLOADPROXY,
    TIMEOUT_1MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_15SEC,
    Images,
)
from utilities.storage import get_downloaded_artifact

LOGGER = logging.getLogger(__name__)
HTTP_UNAUTHORIZED = 401
HTTP_OK = 200


def wait_for_upload_response_code(token, data, response_code, asynchronous=False):
    kwargs = {
        "wait_timeout": TIMEOUT_1MIN,
        "sleep": 5,
        "func": storage_utils.upload_image,
        "token": token,
        "data": data,
    }
    if asynchronous:
        kwargs["asynchronous"] = asynchronous
    sampler = TimeoutSampler(**kwargs)
    for sample in sampler:
        if sample == response_code:
            return True


@pytest.mark.polarion("CNV-2318")
@pytest.mark.s390x
def test_cdi_uploadproxy_route_owner_references(hco_namespace):
    route = Route(name=CDI_UPLOADPROXY, namespace=hco_namespace.name)
    assert route.instance
    assert route.instance["metadata"]["ownerReferences"][0]["name"] == "cdi-deployment"
    assert route.instance["metadata"]["ownerReferences"][0]["kind"] == "Deployment"


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
def test_successful_upload_token_expiry(namespace, data_volume_multi_storage_scope_function):
    dv = data_volume_multi_storage_scope_function
    dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_3MIN)
    with UploadTokenRequest(
        name=dv.name,
        namespace=namespace.name,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        LOGGER.info("Wait until token expires ...")
        time.sleep(310)
        wait_for_upload_response_code(token=token, data="test", response_code=HTTP_UNAUTHORIZED)


def _upload_image(dv_name, namespace, storage_class, local_name, size=None):
    """
    Upload image function for the use of other tests
    """
    size = size or "3Gi"
    with utilities.storage.create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=namespace.name,
        size=size,
        storage_class=storage_class,
    ) as dv:
        LOGGER.info("Wait for DV to be UploadReady")
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_5MIN)
        with UploadTokenRequest(
            name=dv_name,
            namespace=namespace.name,
            pvc_name=dv.pvc.name,
        ) as utr:
            token = utr.create().status.token
            sleep(5)
            LOGGER.info("Ensure upload was successful")
            wait_for_upload_response_code(token=token, data=local_name, response_code=HTTP_OK)


@pytest.mark.sno
@pytest.mark.s390x
@pytest.mark.polarion("CNV-2015")
def test_successful_concurrent_uploads(
    upload_file_path,
    namespace,
    storage_class_matrix__module__,
):
    dvs_processes = []
    storage_class = [*storage_class_matrix__module__][0]
    available_pv = PersistentVolume(name=namespace).max_available_pvs
    for dv in range(available_pv):
        dv_process = multiprocessing.Process(
            target=_upload_image,
            args=(f"dv-{dv}", namespace, storage_class, upload_file_path),
        )
        dv_process.start()
        dvs_processes.append(dv_process)

    for dvs in dvs_processes:
        dvs.join()
        if dvs.exitcode != 0:
            raise pytest.fail("Creating DV exited with non-zero return code")


@pytest.mark.sno
@pytest.mark.parametrize(
    "upload_file_path",
    [
        pytest.param(
            {
                "remote_image_dir": Images.Rhel.DIR,
                "remote_image_name": Images.Rhel.RHEL8_0_IMG,
            },
            marks=(pytest.mark.polarion("CNV-2017")),
        ),
    ],
    indirect=True,
)
def test_successful_upload_missing_file_in_transit(namespace, storage_class_matrix__class__, upload_file_path):
    dv_name = "cnv-2017"
    storage_class = [*storage_class_matrix__class__][0]
    get_downloaded_artifact(
        remote_name=RHEL_LATEST["image_path"],
        local_name=upload_file_path,
    )
    upload_process = multiprocessing.Process(
        target=_upload_image,
        args=(dv_name, namespace, storage_class, upload_file_path, "10Gi"),
    )

    # Run process in parallel
    upload_process.start()

    # Ideally, the file should be removed while the status of upload is 'UploadInProgress'.
    # However, 'UploadInProgress' status phase is not implemented yet.
    time.sleep(TIMEOUT_15SEC)
    sh.rm("-f", upload_file_path)

    # Exit the completed processes
    upload_process.join()


@pytest.mark.sno
@pytest.mark.parametrize(
    "download_specified_image, data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "image_path": py_config["latest_rhel_os_dict"]["image_path"],
                "image_file": py_config["latest_rhel_os_dict"]["image_name"],
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
