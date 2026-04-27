"""
HonorWaitForFirstConsumer test suite
"""

import logging

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from utilities.constants import (
    OS_FLAVOR_RHEL,
    TIMEOUT_2MIN,
    TIMEOUT_30SEC,
    Images,
)
from utilities.storage import (
    add_dv_to_vm,
    check_disk_count_in_vm,
    check_upload_virtctl_result,
    create_dv,
    create_vm_from_dv,
    data_volume_template_with_source_ref_dict,
    virtctl_upload_dv,
)
from utilities.virt import VirtualMachineForTests, running_vm, wait_for_ssh_connectivity

pytestmark = [
    pytest.mark.post_upgrade,
]

LOGGER = logging.getLogger(__name__)


WFFC_DV_NAME = "wffc-dv-name"
DEFAULT_BLANK_DV_SIZE = "1Gi"


@pytest.fixture(scope="module")
def wffc_storage_class_name_scope_module(
    storage_class_matrix_wffc_matrix__module__,
):
    return next(iter(storage_class_matrix_wffc_matrix__module__))


@pytest.fixture()
def blank_dv_wffc_scope_function(request, unprivileged_client, namespace, wffc_storage_class_name_scope_module):
    with create_dv(
        source="blank",
        dv_name=f"dv-{request.param['dv_name']}",
        namespace=namespace.name,
        size=DEFAULT_BLANK_DV_SIZE,
        storage_class=wffc_storage_class_name_scope_module,
        consume_wffc=False,
        client=unprivileged_client,
    ) as dv:
        yield dv


@pytest.fixture()
def blank_dv_template_wffc_scope_function(request, namespace, wffc_storage_class_name_scope_module):
    blank_dv_template = DataVolume(
        name=f"dv-{request.param['dv_name']}",
        namespace=namespace.name,
        source="blank",
        size=DEFAULT_BLANK_DV_SIZE,
        storage_class=wffc_storage_class_name_scope_module,
        api_name="storage",
    )
    blank_dv_template.to_dict()
    return blank_dv_template.res


def validate_vm_and_disk_count(vm):
    running_vm(vm=vm)
    check_disk_count_in_vm(vm=vm)


@pytest.fixture(scope="class")
def uploaded_wffc_dv(namespace, unprivileged_client):
    return DataVolume(namespace=namespace.name, name=WFFC_DV_NAME, client=unprivileged_client)


@pytest.fixture(scope="class")
def uploaded_dv_via_virtctl_wffc(
    namespace,
    downloaded_cirros_image_full_path,
    downloaded_cirros_image_scope_class,
    wffc_storage_class_name_scope_module,
):
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=WFFC_DV_NAME,
        size=Images.Cirros.DEFAULT_DV_SIZE,
        image_path=downloaded_cirros_image_full_path,
        storage_class=wffc_storage_class_name_scope_module,
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
            # No scheduling status in VirtualMachineInstance.Status, using string literal instead
            vm_status = "Scheduling"
            bounded_pvc = pvc.prime_pvc
        else:
            vm_status = VirtualMachineInstance.Status.PENDING
            bounded_pvc = pvc
        vm_dv.vmi.wait_for_status(status=vm_status)
        bounded_pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_30SEC)
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
        wffc_storage_class_name_scope_module,
    ):
        with virtctl_upload_dv(
            client=vm_from_uploaded_dv.client,
            namespace=vm_from_uploaded_dv.namespace,
            name=WFFC_DV_NAME,
            size=Images.Cirros.DEFAULT_DV_SIZE,
            image_path=downloaded_cirros_image_full_path,
            storage_class=wffc_storage_class_name_scope_module,
            insecure=True,
            consume_wffc=False,
            cleanup=False,
        ) as res:
            check_upload_virtctl_result(result=res)
            vm_from_uploaded_dv.vmi.wait_until_running()
            wait_for_ssh_connectivity(vm=vm_from_uploaded_dv, timeout=TIMEOUT_2MIN)
            check_disk_count_in_vm(vm=vm_from_uploaded_dv)


@pytest.mark.sno
@pytest.mark.s390x
@pytest.mark.polarion("CNV-4742")
@pytest.mark.parametrize(
    "blank_dv_wffc_scope_function",
    [
        pytest.param({"dv_name": "blank-wffc-4742"}),
    ],
    indirect=True,
)
def test_wffc_add_dv_to_vm_with_data_volume_template(
    unprivileged_client,
    namespace,
    wffc_storage_class_name_scope_module,
    rhel10_data_source_scope_module,
    blank_dv_wffc_scope_function,
):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="cnv-4742-vm",
        namespace=namespace.name,
        os_flavor=OS_FLAVOR_RHEL,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel10_data_source_scope_module,
            storage_class=wffc_storage_class_name_scope_module,
        ),
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm:
        validate_vm_and_disk_count(vm=vm)
        # Add DV
        vm.stop(wait=True)
        add_dv_to_vm(vm=vm, dv_name=blank_dv_wffc_scope_function.name)
        # Check DV was added
        validate_vm_and_disk_count(vm=vm)


@pytest.mark.sno
@pytest.mark.s390x
@pytest.mark.polarion("CNV-4743")
@pytest.mark.parametrize(
    "blank_dv_template_wffc_scope_function", [pytest.param({"dv_name": "blank-wffc-4743"})], indirect=True
)
def test_wffc_vm_with_two_data_volume_templates(
    unprivileged_client,
    namespace,
    wffc_storage_class_name_scope_module,
    rhel10_data_source_scope_module,
    blank_dv_template_wffc_scope_function,
):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="cnv-4743-vm",
        namespace=namespace.name,
        os_flavor=OS_FLAVOR_RHEL,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel10_data_source_scope_module,
            storage_class=wffc_storage_class_name_scope_module,
        ),
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm:
        add_dv_to_vm(
            vm=vm,
            template_dv=blank_dv_template_wffc_scope_function,
        )
        validate_vm_and_disk_count(vm=vm)
