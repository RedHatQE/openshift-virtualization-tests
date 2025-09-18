# -*- coding: utf-8 -*-

"""
Upload tests
"""

import logging
import multiprocessing
import time
from random import shuffle
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
    QUARANTINED,
    TIMEOUT_1MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_15SEC,
    Images,
)
from utilities.storage import check_disk_count_in_vm, get_downloaded_artifact

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
    namespace,
    tmpdir,
    dv_name,
    remote_name,
    local_name,
    unprivileged_client,
):
    local_name = f"{tmpdir}/{local_name}"
    get_downloaded_artifact(remote_name=remote_name, local_name=local_name)
    with storage_utils.upload_image_to_dv(
        dv_name=dv_name,
        storage_class=py_config["default_storage_class"],
        storage_ns_name=namespace.name,
        client=unprivileged_client,
    ) as dv:
        storage_utils.upload_token_request(storage_ns_name=namespace.name, pvc_name=dv.pvc.name, data=local_name)
        dv.wait_for_dv_success()
        with storage_utils.create_vm_from_dv(dv=dv) as vm_dv:
            check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.xfail(
    reason=f"{QUARANTINED}: Flaky test, timeout failure; CNV-67422",
    run=False,
)
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-2018",
                "source": "upload",
                "dv_size": "3Gi",
                "wait": False,
            },
            marks=(pytest.mark.polarion("CNV-2018")),
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.polarion("CNV-2018")
@pytest.mark.s390x
def test_successful_upload_token_validity(
    namespace,
    data_volume_multi_storage_scope_function,
    upload_file_path,
):
    dv = data_volume_multi_storage_scope_function
    dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_3MIN)
    with UploadTokenRequest(
        name=dv.name,
        namespace=namespace.name,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        wait_for_upload_response_code(token=shuffle(list(token)), data="test", response_code=HTTP_UNAUTHORIZED)
    with UploadTokenRequest(
        name=dv.name,
        namespace=namespace.name,
        pvc_name=dv.pvc.name,
    ) as utr:
        token = utr.create().status.token
        wait_for_upload_response_code(token=token, data=upload_file_path, response_code=HTTP_OK)
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.RUNNING,
            status=DataVolume.Condition.Status.TRUE,
            timeout=TIMEOUT_5MIN,
        )
        dv.wait_for_condition(
            condition=DataVolume.Condition.Type.READY,
            status=DataVolume.Condition.Status.TRUE,
            timeout=TIMEOUT_5MIN,
        )


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
