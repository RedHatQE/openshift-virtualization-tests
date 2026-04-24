import logging

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from pytest_testconfig import config as py_config

from tests.os_params import FEDORA_LATEST_LABELS
from utilities.constants import PVC, TIMEOUT_20MIN
from utilities.storage import ErrorMsg, create_dv, create_dv_with_source_ref, get_dv_size_from_datasource
from utilities.virt import vm_instance_from_template, wait_for_ssh_connectivity

pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def golden_image_dv_from_fedora_datasource_scope_module(
    admin_client,
    golden_images_namespace,
    fedora_data_source_scope_module,
):
    size = get_dv_size_from_datasource(data_source=fedora_data_source_scope_module)
    with create_dv_with_source_ref(
        client=admin_client,
        dv_name=f"golden-image-fedora-{py_config['default_storage_class']}",
        namespace=golden_images_namespace.name,
        size=size,
        storage_class=py_config["default_storage_class"],
        data_source=fedora_data_source_scope_module,
    ) as dv:
        dv.wait_for_dv_success()
        yield dv


@pytest.fixture
def dv_created_by_unprivileged_user_with_rolebinding(
    request,
    golden_images_namespace,
    golden_images_edit_rolebinding,
    unprivileged_client,
    storage_class_name_scope_function,
    fedora_data_source_scope_module,
):
    size = get_dv_size_from_datasource(data_source=fedora_data_source_scope_module)
    with create_dv_with_source_ref(
        client=unprivileged_client,
        dv_name=f"{request.param['dv_name']}-{storage_class_name_scope_function}",
        namespace=golden_images_namespace.name,
        size=size,
        storage_class=storage_class_name_scope_function,
        data_source=fedora_data_source_scope_module,
    ) as dv:
        yield dv


@pytest.fixture()
def fedora_vm_from_datasource_multi_storage_scope_function(
    request,
    unprivileged_client,
    namespace,
    fedora_data_source_scope_module,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=fedora_data_source_scope_module,
    ) as vm:
        yield vm


@pytest.mark.sno
@pytest.mark.polarion("CNV-4755")
def test_regular_user_cant_create_dv_in_ns(
    golden_images_namespace,
    unprivileged_client,
    fedora_data_source_scope_module,
):
    LOGGER.info("Try as a regular user, to create a DV in golden image NS and receive the proper error")
    size = get_dv_size_from_datasource(data_source=fedora_data_source_scope_module)
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with create_dv_with_source_ref(
            dv_name="cnv-4755",
            namespace=golden_images_namespace.name,
            size=size,
            storage_class=py_config["default_storage_class"],
            client=unprivileged_client,
            data_source=fedora_data_source_scope_module,
        ):
            return


@pytest.mark.sno
@pytest.mark.polarion("CNV-4756")
def test_regular_user_cant_delete_dv_from_cloned_dv(
    golden_images_namespace,
    unprivileged_client,
    golden_image_dv_from_fedora_datasource_scope_module,
):
    LOGGER.info("Try as a regular user, to delete a dv from golden image NS and receive the proper error")
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_DELETE_RESOURCE,
    ):
        DataVolume(
            name=golden_image_dv_from_fedora_datasource_scope_module.name,
            namespace=golden_image_dv_from_fedora_datasource_scope_module.namespace,
            client=unprivileged_client,
        ).delete()


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.parametrize(
    "fedora_vm_from_datasource_multi_storage_scope_function",
    [
        pytest.param(
            {
                "vm_name": "fedora-vm",
                "template_labels": FEDORA_LATEST_LABELS,
            },
            marks=pytest.mark.polarion("CNV-4757"),
        ),
    ],
    indirect=True,
)
def test_regular_user_can_create_vm_from_cloned_dv(
    fedora_vm_from_datasource_multi_storage_scope_function,
):
    wait_for_ssh_connectivity(vm=fedora_vm_from_datasource_multi_storage_scope_function)


@pytest.mark.sno
@pytest.mark.polarion("CNV-4758")
def test_regular_user_can_list_all_pvc_in_ns(
    golden_images_namespace,
    unprivileged_client,
    golden_image_dv_from_fedora_datasource_scope_module,
):
    LOGGER.info("Make sure regular user have permissions to view PVC's in golden image NS")
    assert list(
        PersistentVolumeClaim.get(
            dyn_client=unprivileged_client,
            namespace=golden_images_namespace.name,
            field_selector=f"metadata.name=={golden_image_dv_from_fedora_datasource_scope_module.name}",
        )
    )


@pytest.mark.sno
@pytest.mark.polarion("CNV-4760")
def test_regular_user_cant_clone_dv_in_ns(
    unprivileged_client,
    golden_image_dv_from_fedora_datasource_scope_module,
):
    LOGGER.info("Try to clone a DV in the golden image NS and fail with the proper message")

    storage_class = golden_image_dv_from_fedora_datasource_scope_module.storage_class
    golden_images_namespace = golden_image_dv_from_fedora_datasource_scope_module.namespace

    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with create_dv(
            dv_name=f"cnv-4760-{storage_class}",
            namespace=golden_images_namespace,
            source=PVC,
            size=golden_image_dv_from_fedora_datasource_scope_module.size,
            source_pvc=golden_image_dv_from_fedora_datasource_scope_module.pvc.name,
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
def test_regular_user_can_create_dv_in_ns_given_proper_rolebinding(
    dv_created_by_unprivileged_user_with_rolebinding,
):
    LOGGER.info(
        "Once a proper RoleBinding created, that use the os-images.kubevirt.io:edit\
        ClusterRole, a regular user can create a DV in the golden image NS.",
    )
    dv_created_by_unprivileged_user_with_rolebinding.wait_for_dv_success(timeout=TIMEOUT_20MIN)
