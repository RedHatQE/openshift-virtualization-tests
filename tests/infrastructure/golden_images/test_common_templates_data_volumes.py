import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from pytest_testconfig import config as py_config

from tests.infrastructure.golden_images.constants import PVC_NOT_FOUND_ERROR
from tests.os_params import FEDORA_LATEST, FEDORA_LATEST_LABELS, FEDORA_LATEST_OS
from utilities.constants import OS_FLAVOR_FEDORA, QUARANTINED, U1_SMALL, Images
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
def fedora_vm_from_data_source(
    request,
    unprivileged_client,
    golden_images_namespace,
    namespace,
    fedora_data_source,
    storage_class_from_config_different_from_data_source,
):
    with VirtualMachineForTests(
        name="fedora-vm-from-data-source",
        namespace=namespace.name,
        client=unprivileged_client,
        memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source,
            storage_class=storage_class_from_config_different_from_data_source
            if request.param.get("set_storage_class")
            else None,
        ),
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def storage_class_from_config_different_from_data_source(fedora_data_source):
    different_storage_class = next(
        (
            storage_class_name
            for storage_class in py_config["storage_class_matrix"]
            for storage_class_name in storage_class
            if storage_class_name != fedora_data_source.source.instance.spec.storageClassName
        ),
        None,
    )
    if different_storage_class is None:
        pytest.xfail("storage_class_matrix only has 1 storage class defined")
    return different_storage_class


@pytest.fixture(scope="module")
def fedora_data_source(unprivileged_client, golden_images_namespace):
    return DataSource(
        client=unprivileged_client, name=OS_FLAVOR_FEDORA, namespace=golden_images_namespace.name, ensure_exists=True
    )


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
@pytest.mark.s390x
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
@pytest.mark.s390x
def test_vm_with_existing_dv(data_volume_scope_function, vm_from_template_with_existing_dv):
    vm_from_template_with_existing_dv.ssh_exec.executor().is_connective()


@pytest.mark.parametrize(
    "fedora_vm_from_data_source",
    [
        pytest.param(
            {
                "set_storage_class": True,
            },
            marks=pytest.mark.polarion("CNV-5529"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_vm_dv_with_different_sc(
    fedora_vm_from_data_source,
):
    # VM cloned PVC storage class is different from the original golden image storage class
    running_vm(vm=fedora_vm_from_data_source)


@pytest.mark.xfail(
    reason=f"{QUARANTINED}: VM is going into running state which it shouldn't, CNV-68779",
    run=False,
)
@pytest.mark.parametrize(
    "fedora_vm_from_data_source",
    [
        pytest.param(
            {
                "set_storage_class": False,
            },
            marks=pytest.mark.polarion("CNV-7752"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_vm_from_golden_image_missing_default_storage_class(
    removed_default_storage_classes,
    fedora_vm_from_data_source,
):
    fedora_vm_from_data_source.start()
    volume_status = fedora_vm_from_data_source.instance.status.volumeSnapshotStatuses[0]
    status_failing_reason = volume_status.reason
    assert not volume_status.enabled, "Volume creation succeeded, expected failure"
    assert status_failing_reason == PVC_NOT_FOUND_ERROR, (
        f"Reason for failing creation is: {status_failing_reason}, expected: {PVC_NOT_FOUND_ERROR}"
    )
