import logging

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from pytest_testconfig import config as py_config

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS
from utilities.constants import PVC, TIMEOUT_20MIN
from utilities.storage import ErrorMsg, create_dv, get_test_artifact_server_url
from utilities.virt import wait_for_ssh_connectivity

pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)
LATEST_RHEL_IMAGE = RHEL_LATEST["image_path"]
RHEL_IMAGE_SIZE = RHEL_LATEST["dv_size"]


DV_PARAM = {
    "dv_name": "golden-image-dv",
    "image": LATEST_RHEL_IMAGE,
    "dv_size": RHEL_IMAGE_SIZE,
    "storage_class": py_config["default_storage_class"],
}


@pytest.fixture
def dv_created_by_unprivileged_user_with_rolebinding(
    request,
    golden_images_namespace,
    golden_images_edit_rolebinding,
    unprivileged_client,
    storage_class_name_scope_function,
):
    with create_dv(
        client=unprivileged_client,
        dv_name=f"{request.param['dv_name']}-{storage_class_name_scope_function}",
        namespace=golden_images_namespace.name,
        url=f"{get_test_artifact_server_url()}{LATEST_RHEL_IMAGE}",
        size=RHEL_IMAGE_SIZE,
        storage_class=storage_class_name_scope_function,
    ) as dv:
        yield dv


@pytest.mark.sno
@pytest.mark.polarion("CNV-4755")
@pytest.mark.s390x
def test_regular_user_cant_create_dv_in_ns(
    golden_images_namespace,
    unprivileged_client,
):
    LOGGER.info("Try as a regular user, to create a DV in golden image NS and receive the proper error")
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with create_dv(
            dv_name="cnv-4755",
            namespace=golden_images_namespace.name,
            url=f"{get_test_artifact_server_url()}{LATEST_RHEL_IMAGE}",
            size=RHEL_IMAGE_SIZE,
            storage_class=py_config["default_storage_class"],
            client=unprivileged_client,
        ):
            return


@pytest.mark.sno
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module",
    [
        pytest.param(DV_PARAM, marks=pytest.mark.polarion("CNV-4756")),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_regular_user_cant_delete_dv_from_cloned_dv(
    golden_images_namespace,
    unprivileged_client,
    golden_image_data_volume_scope_module,
):
    LOGGER.info("Try as a regular user, to delete a dv from golden image NS and receive the proper error")
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_DELETE_RESOURCE,
    ):
        DataVolume(
            name=golden_image_data_volume_scope_module.name,
            namespace=golden_image_data_volume_scope_module.namespace,
            client=unprivileged_client,
        ).delete()


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_function,"
    "golden_image_vm_instance_from_template_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-4757",
                "image": LATEST_RHEL_IMAGE,
                "dv_size": RHEL_IMAGE_SIZE,
            },
            {
                "vm_name": "rhel-vm",
                "template_labels": RHEL_LATEST_LABELS,
            },
            marks=pytest.mark.polarion("CNV-4757"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_regular_user_can_create_vm_from_cloned_dv(
    golden_image_data_volume_multi_storage_scope_function,
    golden_image_vm_instance_from_template_multi_storage_scope_function,
):
    wait_for_ssh_connectivity(vm=golden_image_vm_instance_from_template_multi_storage_scope_function)


@pytest.mark.sno
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module",
    [
        pytest.param(DV_PARAM, marks=pytest.mark.polarion("CNV-4758")),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_regular_user_can_list_all_pvc_in_ns(
    golden_images_namespace,
    unprivileged_client,
    golden_image_data_volume_scope_module,
):
    LOGGER.info("Make sure regular user have permissions to view PVC's in golden image NS")
    assert list(
        PersistentVolumeClaim.get(
            dyn_client=unprivileged_client,
            namespace=golden_images_namespace.name,
            field_selector=f"metadata.name=={golden_image_data_volume_scope_module.name}",
        )
    )


@pytest.mark.sno
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module",
    [
        pytest.param(DV_PARAM, marks=pytest.mark.polarion("CNV-4760")),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_regular_user_cant_clone_dv_in_ns(
    unprivileged_client,
    golden_image_data_volume_scope_module,
):
    LOGGER.info("Try to clone a DV in the golden image NS and fail with the proper message")

    storage_class = golden_image_data_volume_scope_module.storage_class
    golden_images_namespace = golden_image_data_volume_scope_module.namespace

    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with create_dv(
            dv_name=f"cnv-4760-{storage_class}",
            namespace=golden_images_namespace,
            source=PVC,
            size=golden_image_data_volume_scope_module.size,
            source_pvc=golden_image_data_volume_scope_module.pvc.name,
            source_namespace=golden_images_namespace,
            client=unprivileged_client,
            storage_class=storage_class,
        ):
            return


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.parametrize(
    "dv_created_by_unprivileged_user_with_rolebinding",
    [
        pytest.param(
            {"dv_name": "cnv-5275"},
            marks=pytest.mark.polarion("CNV-5275"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_regular_user_can_create_dv_in_ns_given_proper_rolebinding(
    dv_created_by_unprivileged_user_with_rolebinding,
):
    LOGGER.info(
        "Once a proper RoleBinding created, that use the os-images.kubevirt.io:edit\
        ClusterRole, a regular user can create a DV in the golden image NS.",
    )
    dv_created_by_unprivileged_user_with_rolebinding.wait_for_dv_success(timeout=TIMEOUT_20MIN)
