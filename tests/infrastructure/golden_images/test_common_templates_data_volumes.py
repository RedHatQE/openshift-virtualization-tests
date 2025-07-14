import pytest
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from pytest_testconfig import config as py_config

from tests.infrastructure.golden_images.constants import PVC_NOT_FOUND_ERROR
from tests.os_params import FEDORA_LATEST, FEDORA_LATEST_LABELS, FEDORA_LATEST_OS
from utilities.constants import HOSTPATH_CSI_BASIC, U1_SMALL, Images
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

pytestmark = pytest.mark.post_upgrade


NON_EXISTING_DV_NAME = "non-existing-dv"


@pytest.fixture()
def vm_from_golden_image_multi_storage(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_multi_storage_scope_function,
):
    with VirtualMachineForTests(
        name="vm-from-golden-image",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_image_data_source_multi_storage_scope_function,
        ),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_from_golden_image(
    request,
    unprivileged_client,
    namespace,
    ocs_storage_class,
    golden_image_data_source_scope_function,
):
    use_ocs_storage_class = request.param.get("ocs_storage_class")
    storage_class = ocs_storage_class.name if use_ocs_storage_class else None
    with VirtualMachineForTests(
        name="vm-from-golden-image",
        namespace=namespace.name,
        client=unprivileged_client,
        memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_image_data_source_scope_function, storage_class=storage_class
        ),
    ) as vm:
        yield vm


@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": FEDORA_LATEST_OS,
                "image": FEDORA_LATEST.get("image_path"),
                "dv_size": FEDORA_LATEST.get("dv_size"),
            },
            marks=pytest.mark.polarion("CNV-5582"),
        ),
    ],
    indirect=True,
)
def test_vm_from_golden_image_cluster_default_storage_class(
    updated_default_storage_class_scope_function,
    golden_image_data_volume_multi_storage_scope_function,
    vm_from_golden_image_multi_storage,
):
    vm_from_golden_image_multi_storage.ssh_exec.executor().is_connective()


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_from_template_with_existing_dv",
    [
        pytest.param(
            {
                "dv_name": "dv-fedora",
                "image": FEDORA_LATEST.get("image_path"),
                "storage_class": py_config["default_storage_class"],
                "dv_size": FEDORA_LATEST.get("dv_size"),
            },
            {
                "vm_name": "fedora-vm",
                "template_labels": FEDORA_LATEST_LABELS,
            },
            marks=pytest.mark.polarion("CNV-5530"),
        ),
    ],
    indirect=True,
)
def test_vm_with_existing_dv(data_volume_scope_function, vm_from_template_with_existing_dv):
    vm_from_template_with_existing_dv.ssh_exec.executor().is_connective()


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, vm_from_golden_image",
    [
        pytest.param(
            {
                "dv_name": FEDORA_LATEST_OS,
                "image": FEDORA_LATEST.get("image_path"),
                "storage_class": HOSTPATH_CSI_BASIC,
                "dv_size": FEDORA_LATEST.get("dv_size"),
            },
            {
                "ocs_storage_class": False,
            },
            marks=pytest.mark.polarion("CNV-5529"),
        ),
    ],
    indirect=True,
)
def test_vm_dv_with_different_sc(
    fail_test_if_no_ocs_sc,
    fail_if_no_hostpath_csi_basic_sc,
    vm_from_golden_image,
):
    # VM cloned PVC storage class is different from the original golden image storage class
    running_vm(vm=vm_from_golden_image)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, vm_from_golden_image",
    [
        pytest.param(
            {
                "dv_name": FEDORA_LATEST_OS,
                "image": FEDORA_LATEST.get("image_path"),
                "dv_size": FEDORA_LATEST.get("dv_size"),
                "storage_class": py_config["default_storage_class"],
            },
            {
                "ocs_storage_class": True,
            },
            marks=pytest.mark.polarion("CNV-7752"),
        ),
    ],
    indirect=True,
)
def test_vm_from_golden_image_missing_default_storage_class(
    removed_default_storage_classes,
    vm_from_golden_image,
):
    vm_from_golden_image.start()
    volume_status = vm_from_golden_image.instance.status.volumeSnapshotStatuses[0]
    status_failing_reason = volume_status.reason
    assert not volume_status.enabled, "Volume creation succeeded, expected failure"
    assert status_failing_reason == PVC_NOT_FOUND_ERROR, (
        f"Reason for failing creation is: {status_failing_reason}, expected: {PVC_NOT_FOUND_ERROR}"
    )
