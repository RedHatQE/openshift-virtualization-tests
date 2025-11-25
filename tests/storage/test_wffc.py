# -*- coding: utf-8 -*-

"""
HonorWaitForFirstConsumer test suite
"""

import logging

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from tests.storage.constants import CIRROS_QCOW2_IMG
from utilities.artifactory import get_artifactory_config_map, get_artifactory_secret, get_test_artifact_server_url
from utilities.constants import (
    TIMEOUT_2MIN,
    TIMEOUT_4MIN,
    TIMEOUT_10SEC,
    Images,
)
from utilities.storage import (
    add_dv_to_vm,
    check_disk_count_in_vm,
    check_upload_virtctl_result,
    create_dv,
    create_vm_from_dv,
    data_volume,
    virtctl_upload_dv,
)
from utilities.virt import VirtualMachineForTests, running_vm, wait_for_ssh_connectivity

pytestmark = [
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
def uploaded_wffc_dv(namespace, unprivileged_client):
    return DataVolume(namespace=namespace.name, name=WFFC_DV_NAME, client=unprivileged_client)


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
def vm_from_uploaded_dv(namespace, uploaded_dv_via_virtctl_wffc, uploaded_wffc_dv, unprivileged_client):
    with create_vm_from_dv(
        dv=uploaded_wffc_dv,
        vm_name=WFFC_DV_NAME,
        start=False,
        client=unprivileged_client,
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
    unprivileged_client,
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
        create_vm_from_dv(client=unprivileged_client, dv=dv, vm_name=dv_name)


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
def test_wffc_clone_dv(unprivileged_client, data_volume_multi_wffc_storage_scope_module):
    with create_dv(
        client=unprivileged_client,
        source="pvc",
        dv_name="dv-target",
        namespace=data_volume_multi_wffc_storage_scope_module.namespace,
        size=data_volume_multi_wffc_storage_scope_module.size,
        source_pvc=data_volume_multi_wffc_storage_scope_module.name,
        storage_class=data_volume_multi_wffc_storage_scope_module.storage_class,
        consume_wffc=True,
    ) as cdv:
        cdv.wait_for_dv_success(timeout=TIMEOUT_4MIN)
        create_vm_from_dv(client=unprivileged_client, dv=cdv, vm_name=cdv.name)


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
    unprivileged_client,
    namespace,
    data_volume_multi_wffc_storage_scope_function,
):
    with VirtualMachineForTests(
        client=unprivileged_client,
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
    unprivileged_client,
    namespace,
    storage_class_matrix_wffc_matrix__module__,
):
    storage_class = [*storage_class_matrix_wffc_matrix__module__][0]
    with VirtualMachineForTests(
        client=unprivileged_client,
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
