"""
Test suite to verify the Hostpath Provisioner CSI Custom Resource permutations
"""

import io
import logging
import os

import pytest
import yaml
from ocp_resources.hostpath_provisioner import HostPathProvisioner
from ocp_resources.storage_class import StorageClass

from tests.storage.hpp.utils import (
    check_disk_count_in_vm_and_image_location,
    cirros_dv_on_hpp,
    is_hpp_cr_with_pvc_template,
    verify_hpp_cr_deleted_successfully,
    verify_hpp_cr_installed_successfully,
)
from tests.storage.utils import create_vm_from_dv
from utilities.storage import HppCsiStorageClass

LOGGER = logging.getLogger(__name__)

SC_NAME = HppCsiStorageClass.Name
SC_POOL = HppCsiStorageClass.StoragePool

STORAGE_CLASS_TO_STORAGE_POOL_MAPPING = {
    SC_NAME.HOSTPATH_CSI_BASIC: SC_POOL.HOSTPATH_CSI_BASIC,
    SC_NAME.HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS: SC_POOL.HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS,
    SC_NAME.HOSTPATH_CSI_PVC_TEMPLATE_OCS_BLOCK: SC_POOL.HOSTPATH_CSI_PVC_TEMPLATE_OCS_BLOCK,
}

pytestmark = pytest.mark.usefixtures("skip_test_if_no_hpp_requested")


@pytest.fixture(scope="module")
def deteled_hostpath_provisioner_cr(admin_client, hco_namespace, schedulable_nodes, hostpath_provisioner_scope_module):
    if hostpath_provisioner_scope_module.exists:
        yaml_object = io.StringIO(yaml.dump(hostpath_provisioner_scope_module.instance.to_dict()))
        LOGGER.warning(f"Custom Resource {HostPathProvisioner.Name.HOSTPATH_PROVISIONER} already exists, deleting it")
        is_cr_with_pvc_template = is_hpp_cr_with_pvc_template(hpp_custom_resource=hostpath_provisioner_scope_module)
        hostpath_provisioner_scope_module.clean_up()
        verify_hpp_cr_deleted_successfully(
            hco_namespace=hco_namespace,
            schedulable_nodes=schedulable_nodes,
            client=admin_client,
            is_hpp_cr_with_pvc_template=is_cr_with_pvc_template,
        )
        yield
        # Recreate HPP CR after the test if it was deleted
        recreated_hpp_cr = HostPathProvisioner(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)
        recreated_hpp_cr.yaml_file = yaml_object
        recreated_hpp_cr.deploy()
        verify_hpp_cr_installed_successfully(
            hco_namespace=hco_namespace,
            schedulable_nodes=schedulable_nodes,
            client=admin_client,
            hpp_custom_resource=recreated_hpp_cr,
        )
    else:
        yield


@pytest.fixture()
def hpp_csi_custom_resource(
    request,
    admin_client,
    schedulable_nodes,
    hco_namespace,
    deteled_hostpath_provisioner_cr,
):
    """
    Creates HPP CSI Custom resource from yaml
    """
    file_path = os.path.abspath(f"tests/storage/hpp/manifests/{request.param}")
    assert os.path.exists(file_path)

    is_cr_with_pvc_template = False
    with HostPathProvisioner(yaml_file=file_path) as hpp_csi_cr:
        is_cr_with_pvc_template = is_hpp_cr_with_pvc_template(hpp_custom_resource=hpp_csi_cr)
        verify_hpp_cr_installed_successfully(
            hco_namespace=hco_namespace,
            schedulable_nodes=schedulable_nodes,
            client=admin_client,
            hpp_custom_resource=hpp_csi_cr,
        )
        yield hpp_csi_cr

    verify_hpp_cr_deleted_successfully(
        hco_namespace=hco_namespace,
        schedulable_nodes=schedulable_nodes,
        client=admin_client,
        is_hpp_cr_with_pvc_template=is_cr_with_pvc_template,
    )


@pytest.fixture(scope="module")
def deleted_hpp_storage_classes(request, cluster_storage_classes):
    deleted_storage_classes_list = []
    for storage_class in request.param:
        storage_class_object = StorageClass(name=storage_class)
        if storage_class_object.exists:
            yaml_object = io.StringIO(yaml.dump(storage_class_object.instance.to_dict()))
            storage_class_object.clean_up()
            deleted_storage_classes_list.append((storage_class_object, yaml_object))
    yield
    # Recreate HPP Storage class after the test if it was deleted
    for storage_class_object, yaml_object in deleted_storage_classes_list:
        storage_class_object.yaml_file = yaml_object
        storage_class_object.deploy()


@pytest.fixture()
def hpp_csi_storage_classes(request, cluster_storage_classes):
    created_storage_classes_dict = {}
    for storage_class in request.param:
        sc = HppCsiStorageClass(
            name=storage_class,
            storage_pool=STORAGE_CLASS_TO_STORAGE_POOL_MAPPING[storage_class],
        )
        sc.deploy()
        if HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC == storage_class:
            created_storage_classes_dict["basic"] = sc
        elif HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS == storage_class:
            created_storage_classes_dict["pvc-ocs-fs"] = sc
        elif HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_BLOCK == storage_class:
            created_storage_classes_dict["pvc-ocs-block"] = sc
    yield created_storage_classes_dict

    for _storage_class in created_storage_classes_dict.values():
        _storage_class.clean_up()


@pytest.fixture()
def cirros_data_volume_on_hpp_basic(request, namespace):
    with cirros_dv_on_hpp(
        dv_name=request.param["dv_name"],
        storage_class=request.param["storage_class"],
        namespace=namespace,
    ) as dv:
        yield dv


@pytest.fixture()
def vm_from_template_with_existing_dv_on_hpp_basic(
    cirros_data_volume_on_hpp_basic,
):
    with create_vm_from_dv(dv=cirros_data_volume_on_hpp_basic) as vm:
        yield vm


@pytest.fixture()
def cirros_data_volume_on_hpp_pvc(request, namespace):
    with cirros_dv_on_hpp(
        dv_name=request.param["dv_name"],
        storage_class=request.param["storage_class"],
        namespace=namespace,
    ) as dv:
        yield dv


@pytest.fixture()
def vm_from_template_with_existing_dv_on_hpp_pvc(
    cirros_data_volume_on_hpp_pvc,
):
    with create_vm_from_dv(dv=cirros_data_volume_on_hpp_pvc) as vm:
        yield vm


@pytest.mark.parametrize(
    "hpp_csi_custom_resource, deleted_hpp_storage_classes, hpp_csi_storage_classes, cirros_data_volume_on_hpp_basic",
    [
        pytest.param(
            "hpp-cr-basic.yaml",
            [HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC],
            [HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC],
            {
                "dv_name": "dv-cnv-7834",
                "storage_class": HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
            },
            marks=pytest.mark.polarion("CNV-7834"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_install_and_delete_hpp_csi_cr_basic(
    admin_client,
    hpp_csi_custom_resource,
    deleted_hpp_storage_classes,
    hpp_csi_storage_classes,
    utility_pods_for_hpp_test,
    cirros_data_volume_on_hpp_basic,
    vm_from_template_with_existing_dv_on_hpp_basic,
):
    check_disk_count_in_vm_and_image_location(
        vm=vm_from_template_with_existing_dv_on_hpp_basic,
        dv=cirros_data_volume_on_hpp_basic,
        hpp_csi_storage_class=hpp_csi_storage_classes["basic"],
        admin_client=admin_client,
    )


@pytest.mark.parametrize(
    "hpp_csi_custom_resource, deleted_hpp_storage_classes, hpp_csi_storage_classes, cirros_data_volume_on_hpp_pvc",
    [
        pytest.param(
            "hpp-cr-pvc_template_ocs_fs.yaml",
            [
                HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
                HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS,
            ],
            [
                HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
                HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS,
            ],
            {
                "dv_name": "dv-cnv-7967-pvc-ocs-fs",
                "storage_class": HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS,
            },
            marks=pytest.mark.polarion("CNV-7967"),
        ),
        pytest.param(
            "hpp-cr-pvc_template_ocs_block.yaml",
            [
                HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
                HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_BLOCK,
            ],
            [
                HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
                HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_BLOCK,
            ],
            {
                "dv_name": "dv-cnv-8899-pvc-ocs-block",
                "storage_class": HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_BLOCK,
            },
            marks=pytest.mark.polarion("CNV-8899"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_install_and_delete_hpp_csi_cr_with_pvc_template(
    admin_client,
    hpp_csi_custom_resource,
    deleted_hpp_storage_classes,
    hpp_csi_storage_classes,
    utility_pods_for_hpp_test,
    cirros_data_volume_on_hpp_pvc,
    vm_from_template_with_existing_dv_on_hpp_pvc,
):
    storage_class = hpp_csi_storage_classes.get("pvc-ocs-fs", hpp_csi_storage_classes.get("pvc-ocs-block"))
    check_disk_count_in_vm_and_image_location(
        vm=vm_from_template_with_existing_dv_on_hpp_pvc,
        dv=cirros_data_volume_on_hpp_pvc,
        hpp_csi_storage_class=storage_class,
        admin_client=admin_client,
    )


@pytest.mark.parametrize(
    "hpp_csi_custom_resource, deleted_hpp_storage_classes, hpp_csi_storage_classes, "
    "cirros_data_volume_on_hpp_basic, cirros_data_volume_on_hpp_pvc",
    [
        pytest.param(
            "hpp-cr-basic_and_pvc_template_ocs_fs.yaml",
            [
                HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
                HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS,
            ],
            [
                HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
                HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS,
            ],
            {
                "dv_name": "dv-cnv-7832-basic",
                "storage_class": HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
            },
            {
                "dv_name": "dv-cnv-7832-pvc",
                "storage_class": HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS,
            },
            marks=pytest.mark.polarion("CNV-7832"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_install_and_delete_hpp_csi_cr_basic_and_with_pvc_template(
    admin_client,
    hpp_csi_custom_resource,
    deleted_hpp_storage_classes,
    hpp_csi_storage_classes,
    utility_pods_for_hpp_test,
    cirros_data_volume_on_hpp_basic,
    vm_from_template_with_existing_dv_on_hpp_basic,
    cirros_data_volume_on_hpp_pvc,
    vm_from_template_with_existing_dv_on_hpp_pvc,
):
    check_disk_count_in_vm_and_image_location(
        vm=vm_from_template_with_existing_dv_on_hpp_basic,
        dv=cirros_data_volume_on_hpp_basic,
        hpp_csi_storage_class=hpp_csi_storage_classes["basic"],
        admin_client=admin_client,
    )
    check_disk_count_in_vm_and_image_location(
        vm=vm_from_template_with_existing_dv_on_hpp_pvc,
        dv=cirros_data_volume_on_hpp_pvc,
        hpp_csi_storage_class=hpp_csi_storage_classes["pvc-ocs-fs"],
        admin_client=admin_client,
    )
