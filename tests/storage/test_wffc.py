# -*- coding: utf-8 -*-

"""
HonorWaitForFirstConsumer test suite
"""

import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from tests.storage.constants import CIRROS_QCOW2_IMG
from tests.storage.utils import create_vm_from_dv, upload_image_to_dv, upload_token_request
from utilities.constants import (
    TIMEOUT_2MIN,
    TIMEOUT_4MIN,
    TIMEOUT_10SEC,
    Images,
)
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    hco_cr_jsonpatch_annotations_dict,
)
from utilities.infra import get_artifactory_config_map, get_artifactory_secret
from utilities.storage import (
    add_dv_to_vm,
    cdi_feature_gate_list_with_added_feature,
    check_cdi_feature_gate_enabled,
    check_disk_count_in_vm,
    check_upload_virtctl_result,
    create_dv,
    data_volume,
    get_downloaded_artifact,
    get_test_artifact_server_url,
    virtctl_upload_dv,
)
from utilities.virt import VirtualMachineForTests, running_vm, wait_for_ssh_connectivity

pytestmark = [
    pytest.mark.usefixtures("enable_wffc_feature_gate"),
    pytest.mark.post_upgrade,
]

LOGGER = logging.getLogger(__name__)


WFFC_DV_NAME = "wffc-dv-name"
DV_PARAMS = {
    "dv_name": "dv-wffc-tests",
    "image": CIRROS_QCOW2_IMG,
    "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
}


@pytest.fixture(scope="module")
def enable_wffc_feature_gate(hyperconverged_resource_scope_module, cdi_config):
    honor_wffc = "HonorWaitForFirstConsumer"
    if check_cdi_feature_gate_enabled(feature=honor_wffc):
        yield
    else:
        # Feature gate wasn't enabled
        with ResourceEditorValidateHCOReconcile(
            patches={
                hyperconverged_resource_scope_module: hco_cr_jsonpatch_annotations_dict(
                    component="cdi",
                    path="featureGates",
                    value=cdi_feature_gate_list_with_added_feature(feature=honor_wffc),
                    op="replace",
                )
            },
            list_resource_reconcile=[CDI],
        ):
            yield


@pytest.fixture(scope="module")
def data_volume_multi_wffc_storage_scope_module(
    request,
    namespace,
    storage_class_matrix_wffc_matrix__module__,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class=[*storage_class_matrix_wffc_matrix__module__][0],
    )


@pytest.fixture()
def data_volume_multi_wffc_storage_scope_function(
    request,
    namespace,
    storage_class_matrix_wffc_matrix__module__,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class=[*storage_class_matrix_wffc_matrix__module__][0],
    )


def get_dv_template_dict(namespace, dv_name, storage_class):
    artifactory_secret = get_artifactory_secret(namespace=namespace)
    artifactory_config_map = get_artifactory_config_map(namespace=namespace)
    return {
        "metadata": {
            "name": f"{dv_name}",
        },
        "spec": {
            "storage": {
                "resources": {"requests": {"storage": Images.Cirros.DEFAULT_DV_SIZE}},
                "storageClassName": storage_class,
            },
            "source": {
                "http": {
                    "certConfigMap": artifactory_config_map.name,
                    "secretRef": artifactory_secret.name,
                    "url": f"{get_test_artifact_server_url()}{CIRROS_QCOW2_IMG}",
                }
            },
        },
    }


def validate_vm_and_disk_count(vm):
    running_vm(vm=vm, wait_for_interfaces=False)
    check_disk_count_in_vm(vm=vm)


@pytest.fixture(scope="class")
def uploaded_wffc_dv(namespace):
    return DataVolume(namespace=namespace.name, name=WFFC_DV_NAME)


@pytest.fixture(scope="class")
def uploaded_dv_via_virtctl_wffc(
    namespace,
    downloaded_cirros_image_full_path,
    downloaded_cirros_image_scope_class,
    storage_class_matrix_wffc_matrix__module__,
):
    with virtctl_upload_dv(
        namespace=namespace.name,
        name=WFFC_DV_NAME,
        size=Images.Cirros.DEFAULT_DV_SIZE,
        image_path=downloaded_cirros_image_full_path,
        storage_class=[*storage_class_matrix_wffc_matrix__module__][0],
        insecure=True,
        consume_wffc=False,
    ) as res:
        yield res


@pytest.fixture()
def vm_from_uploaded_dv(namespace, uploaded_dv_via_virtctl_wffc, uploaded_wffc_dv):
    with create_vm_from_dv(
        dv=uploaded_wffc_dv,
        vm_name=WFFC_DV_NAME,
        start=False,
    ) as vm_dv:
        pvc = uploaded_wffc_dv.pvc
        vm_dv.start(wait=False)
        if pvc.use_populator:
            vm_status = VirtualMachineInstance.Status.SCHEDULING
            bounded_pvc = pvc.prime_pvc
        else:
            vm_status = VirtualMachineInstance.Status.PENDING
            bounded_pvc = pvc
        vm_dv.vmi.wait_for_status(status=vm_status)
        bounded_pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_10SEC)
        uploaded_wffc_dv.wait_for_status(status=uploaded_wffc_dv.Status.UPLOAD_READY)
        yield vm_dv


class TestWFFCUploadVirtctl:
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-4711")
    @pytest.mark.s390x
    def test_wffc_fail_to_upload_dv_via_virtctl(
        self,
        namespace,
        uploaded_dv_via_virtctl_wffc,
        uploaded_wffc_dv,
    ):
        check_upload_virtctl_result(
            result=uploaded_dv_via_virtctl_wffc,
            expected_success=False,
            expected_output=(
                f"cannot upload to DataVolume in {uploaded_wffc_dv.Status.PENDING_POPULATION} phase, "
                "make sure the PVC is Bound, or use force-bind flag"
            ),
            assert_message="Upload DV via virtctl, with wffc SC binding mode ended up with success instead of failure",
        )
        uploaded_dv_pvc = uploaded_wffc_dv.pvc
        assert uploaded_dv_pvc.status == uploaded_dv_pvc.Status.PENDING, (
            f"The status of PVC {uploaded_dv_pvc.name}:{uploaded_dv_pvc.status} and not "
            "{uploaded_dv_pvc.Status.PENDING}"
        )
        assert uploaded_wffc_dv.status == uploaded_wffc_dv.Status.PENDING_POPULATION, (
            f"The status of DV {uploaded_wffc_dv.name}:{uploaded_wffc_dv.status} and not "
            f"{uploaded_wffc_dv.Status.PENDING_POPULATION}"
        )

    @pytest.mark.sno
    @pytest.mark.polarion("CNV-7413")
    @pytest.mark.s390x
    def test_wffc_create_vm_from_uploaded_dv_via_virtctl(
        self,
        downloaded_cirros_image_full_path,
        vm_from_uploaded_dv,
        storage_class_matrix_wffc_matrix__module__,
    ):
        with virtctl_upload_dv(
            namespace=vm_from_uploaded_dv.namespace,
            name=WFFC_DV_NAME,
            size=Images.Cirros.DEFAULT_DV_SIZE,
            image_path=downloaded_cirros_image_full_path,
            storage_class=[*storage_class_matrix_wffc_matrix__module__][0],
            insecure=True,
            consume_wffc=False,
            cleanup=False,
        ) as res:
            check_upload_virtctl_result(result=res)
            vm_from_uploaded_dv.vmi.wait_until_running()
            wait_for_ssh_connectivity(vm=vm_from_uploaded_dv, timeout=TIMEOUT_2MIN)
            check_disk_count_in_vm(vm=vm_from_uploaded_dv)


@pytest.mark.sno
@pytest.mark.polarion("CNV-4739")
@pytest.mark.s390x
def test_wffc_import_registry_dv(
    namespace,
    storage_class_matrix_wffc_matrix__module__,
):
    dv_name = "cnv-4739"
    with create_dv(
        source="registry",
        dv_name=dv_name,
        namespace=namespace.name,
        url=f"docker://quay.io/kubevirt/{Images.Cirros.DISK_DEMO}",
        storage_class=[*storage_class_matrix_wffc_matrix__module__][0],
        consume_wffc=True,
    ) as dv:
        dv.wait_for_dv_success()
        with create_vm_from_dv(dv=dv, vm_name=dv_name) as vm_dv:
            check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.sno
@pytest.mark.polarion("CNV-4741")
@pytest.mark.s390x
def test_wffc_upload_dv_via_token(
    unprivileged_client,
    namespace,
    tmpdir,
    storage_class_matrix_wffc_matrix__module__,
):
    dv_name = "cnv-4741"
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    get_downloaded_artifact(
        remote_name=CIRROS_QCOW2_IMG,
        local_name=local_name,
    )
    with upload_image_to_dv(
        dv_name=dv_name,
        storage_class=[*storage_class_matrix_wffc_matrix__module__][0],
        storage_ns_name=namespace.name,
        client=unprivileged_client,
        consume_wffc=True,
    ) as dv:
        upload_token_request(storage_ns_name=namespace.name, pvc_name=dv.pvc.name, data=local_name)
        dv.wait_for_dv_success()
        with create_vm_from_dv(dv=dv, vm_name=dv_name) as vm_dv:
            check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_wffc_storage_scope_module",
    [
        pytest.param(
            {**DV_PARAMS, **{"consume_wffc": True}},
            marks=pytest.mark.polarion("CNV-4371"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_wffc_import_http_dv(data_volume_multi_wffc_storage_scope_module):
    with create_vm_from_dv(
        dv=data_volume_multi_wffc_storage_scope_module, vm_name=data_volume_multi_wffc_storage_scope_module.name
    ) as vm_dv:
        check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_wffc_storage_scope_module",
    [
        pytest.param(
            {**DV_PARAMS, **{"consume_wffc": True}},
            marks=pytest.mark.polarion("CNV-4379"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_wffc_clone_dv(data_volume_multi_wffc_storage_scope_module):
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=data_volume_multi_wffc_storage_scope_module.namespace,
        size=data_volume_multi_wffc_storage_scope_module.size,
        source_pvc=data_volume_multi_wffc_storage_scope_module.name,
        storage_class=data_volume_multi_wffc_storage_scope_module.storage_class,
        consume_wffc=True,
    ) as cdv:
        cdv.wait_for_dv_success(timeout=TIMEOUT_4MIN)
        with create_vm_from_dv(dv=cdv, vm_name=cdv.name) as vm_dv:
            check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_wffc_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-wffc-4742",
                "image": CIRROS_QCOW2_IMG,
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
                "consume_wffc": False,
            },
            marks=pytest.mark.polarion("CNV-4742"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_wffc_add_dv_to_vm_with_data_volume_template(
    namespace,
    data_volume_multi_wffc_storage_scope_function,
):
    with VirtualMachineForTests(
        name="cnv-4742-vm",
        namespace=namespace.name,
        os_flavor=Images.Cirros.OS_FLAVOR,
        data_volume_template=get_dv_template_dict(
            namespace=namespace.name,
            dv_name="template-dv",
            storage_class=data_volume_multi_wffc_storage_scope_function.storage_class,
        ),
        memory_guest=Images.Cirros.DEFAULT_MEMORY_SIZE,
    ) as vm:
        validate_vm_and_disk_count(vm=vm)
        # Add DV
        vm.stop(wait=True)
        add_dv_to_vm(vm=vm, dv_name=data_volume_multi_wffc_storage_scope_function.name)
        # Check DV was added
        validate_vm_and_disk_count(vm=vm)


@pytest.mark.sno
@pytest.mark.polarion("CNV-4743")
@pytest.mark.s390x
def test_wffc_vm_with_two_data_volume_templates(
    namespace,
    storage_class_matrix_wffc_matrix__module__,
):
    storage_class = [*storage_class_matrix_wffc_matrix__module__][0]
    with VirtualMachineForTests(
        name="cnv-4743-vm",
        namespace=namespace.name,
        os_flavor=Images.Cirros.OS_FLAVOR,
        data_volume_template=get_dv_template_dict(
            namespace=namespace.name,
            dv_name="template-dv-1",
            storage_class=storage_class,
        ),
        memory_guest=Images.Cirros.DEFAULT_MEMORY_SIZE,
    ) as vm:
        add_dv_to_vm(
            vm=vm,
            template_dv=get_dv_template_dict(
                namespace=namespace.name,
                dv_name="template-dv-2",
                storage_class=storage_class,
            ),
        )
        validate_vm_and_disk_count(vm=vm)
