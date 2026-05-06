"""
CDI Import
"""

import logging
import uuid

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork

from utilities.constants import TIMEOUT_2MIN, TIMEOUT_40MIN, Images
from libs.net.ip import random_ipv4_address
from libs.net.udn import create_udn_namespace
from utilities.constants import Images
from utilities.constants.timeouts import TIMEOUT_1MIN, TIMEOUT_2MIN
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_test_artifact_server_url,
)
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_2MIN, WIN_2K22, Images
from utilities.os_utils import get_windows_container_disk_path
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
@pytest.fixture(scope="module")
def udn_namespace_for_dv_upload(admin_client):
    yield from create_udn_namespace(name="test-cdi-upload-udn-ns", client=admin_client)


@pytest.fixture(scope="module")
def primary_udn_for_upload(admin_client, udn_namespace_for_dv_upload):
    with Layer2UserDefinedNetwork(
        name="layer2-udn-upload",
        namespace=udn_namespace_for_dv_upload.name,
        role="Primary",
        subnets=[f"{random_ipv4_address(net_seed=0, host_address=0)}/24"],
        ipam={"lifecycle": "Persistent"},
        client=admin_client,
    ) as udn:
        udn.wait_for_condition(
            condition="NetworkAllocationSucceeded",
            status=udn.Condition.Status.TRUE,
        )
        yield udn
@pytest.fixture()
def windows_dv_from_registry(
    unprivileged_client,
    namespace,
    storage_class_name_immediate_binding_scope_module,
):
    """
    Creates a Windows Server 2022 DataVolume from registry for testing VM creation.
    This avoids the upload process and SSH configuration issues with uploaded Windows images.
    """
    artifactory_secret = get_artifactory_secret(namespace=namespace.name)
    artifactory_config_map = get_artifactory_config_map(namespace=namespace.name)
    with create_dv(
        client=unprivileged_client,
        dv_name="windows-2022-registry-dv",
        namespace=namespace.name,
        source="registry",
        size=Images.Windows.CONTAINER_DISK_DV_SIZE,
        storage_class=storage_class_name_immediate_binding_scope_module,
        url=f"{get_test_artifact_server_url(schema='registry')}/{get_windows_container_disk_path(os_value=WIN_2K22)}",
        secret=artifactory_secret,
        cert_configmap=artifactory_config_map.name,
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_2MIN)
        yield dv
    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
    )
