"""
CDI Import
"""

import logging
import uuid

import pytest
from ocp_resources.datavolume import DataVolume

from utilities.constants import TIMEOUT_2MIN, TIMEOUT_40MIN, Images
from utilities.storage import check_upload_virtctl_result, create_dv, get_downloaded_artifact, virtctl_upload_dv

LOGGER = logging.getLogger(__name__)
DEFAULT_DV_SIZE = Images.Cdi.DEFAULT_DV_SIZE
LOCAL_PATH = f"/tmp/{Images.Cdi.QCOW2_IMG}"


@pytest.fixture(scope="function")
def upload_file_path(request, tmpdir):
    params = request.param if hasattr(request, "param") else {}
    remote_image_dir = params.get("remote_image_dir", Images.Cirros.DIR)
    remote_image_name = params.get("remote_image_name", Images.Cirros.QCOW2_IMG)
    local_name = f"{tmpdir}/{remote_image_name}"
    get_downloaded_artifact(
        remote_name=f"{remote_image_dir}/{remote_image_name}",
        local_name=local_name,
    )
    yield local_name


@pytest.fixture()
def download_specified_image(request, tmpdir_factory):
    local_path = tmpdir_factory.mktemp("cdi_upload").join(request.param.get("image_file"))
    get_downloaded_artifact(remote_name=request.param.get("image_path"), local_name=local_path)
    return local_path


@pytest.fixture(scope="class")
def uploaded_dv_scope_class(unprivileged_client, namespace, storage_class_name_scope_class):
    dv_name = f"upload-existing-dv-{str(uuid.uuid4())[:8]}"
    get_downloaded_artifact(
        remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}",
        local_name=LOCAL_PATH,
    )
    with create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=namespace.name,
        size=DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_class,
        client=unprivileged_client,
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_2MIN)
        with virtctl_upload_dv(
            client=namespace.client,
            namespace=namespace.name,
            name=dv.name,
            size=DEFAULT_DV_SIZE,
            image_path=LOCAL_PATH,
            insecure=True,
            storage_class=storage_class_name_scope_class,
            no_create=True,
        ) as upload_result:
            check_upload_virtctl_result(result=upload_result)
            yield dv


@pytest.fixture()
def uploaded_windows_dv(
    unprivileged_client,
    namespace,
    storage_class_name_immediate_binding_scope_module,
    tmpdir_factory,
):
    local_path = str(tmpdir_factory.mktemp("cdi_upload").join(Images.Windows.WIN2022_IMG))
    get_downloaded_artifact(
        remote_name=f"{Images.Windows.DIR}/{Images.Windows.WIN2022_IMG}",
        local_name=local_path,
    )
    dv_name = "dv-win2022-uploaded"
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=dv_name,
        size=Images.Windows.DEFAULT_DV_SIZE,
        image_path=local_path,
        storage_class=storage_class_name_immediate_binding_scope_module,
        insecure=True,
    ) as upload_result:
        check_upload_virtctl_result(result=upload_result)
        dv = DataVolume(namespace=namespace.name, name=dv_name, client=unprivileged_client)
        dv.wait_for_dv_success(timeout=TIMEOUT_40MIN)
        yield dv
