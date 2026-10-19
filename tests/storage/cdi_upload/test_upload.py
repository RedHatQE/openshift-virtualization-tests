"""
Upload tests
"""

import logging
from random import shuffle

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.route import Route
from ocp_resources.upload_token_request import UploadTokenRequest
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutSampler
from utilities.constants.components import CDI_UPLOADPROXY
from utilities.constants.timeouts import TIMEOUT_1MIN, TIMEOUT_3MIN

import tests.storage.utils as storage_utils
from tests.storage.stop_status_utils import dv_stop_status_restart_threshold
from utilities.constants import Images
from utilities.storage import create_vm_from_dv, get_downloaded_artifact

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
    unprivileged_client, namespace, tmpdir, dv_name, remote_name, local_name
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
            {"dv_name": "cnv-2018", "source": "upload", "dv_size": Images.Cirros.DEFAULT_DV_SIZE, "wait": False},
            marks=(pytest.mark.polarion("CNV-2018")),
        )
    ],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.polarion("CNV-2018")
@pytest.mark.s390x
def test_successful_upload_token_validity(
    unprivileged_client, namespace, data_volume_multi_storage_scope_function, upload_file_path
):
    dv = data_volume_multi_storage_scope_function
    dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_3MIN)
    with UploadTokenRequest(
        client=unprivileged_client, name=dv.name, namespace=namespace.name, pvc_name=dv.pvc.name
    ) as utr:
        token = utr.create().status.token
        wait_for_upload_response_code(token=shuffle(list(token)), data="test", response_code=HTTP_UNAUTHORIZED)
    with UploadTokenRequest(
        client=unprivileged_client, name=dv.name, namespace=namespace.name, pvc_name=dv.pvc.name
    ) as utr:
        token = utr.create().status.token
        wait_for_upload_response_code(token=token, data=upload_file_path, response_code=HTTP_OK)
        dv.wait_for_dv_success(stop_status_func=dv_stop_status_restart_threshold, dv=dv)
