import pytest
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from pytest_testconfig import py_config

from tests.infrastructure.instance_types.constants import ALL_OPTIONS_VM_PREFERENCE_SPEC
from utilities.constants import Images
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests

PREFERENCE_STORAGE_CLASS = py_config["default_storage_class"]


# in PVC api accessModes are needed and the resources request should be in the pvc field
def pvc_api_adjustments(dv_template):
    storage_profile_info = StorageProfile(name=PREFERENCE_STORAGE_CLASS).instance.status["claimPropertySets"][0]
    dv_template["spec"]["pvc"] = {
        "volumeMode": storage_profile_info["volumeMode"],
        "accessModes": storage_profile_info["accessModes"],
        "resources": {"requests": {"storage": dv_template["spec"]["storage"]["resources"]["requests"]["storage"]}},
    }
    del dv_template["spec"]["storage"]
    return dv_template


@pytest.fixture(scope="class")
def vm_storage_class_preference():
    with VirtualMachineClusterPreference(
        name="storage-class-vm-preference",
        volumes={"preferredStorageClassName": PREFERENCE_STORAGE_CLASS},
    ) as vm_cluster_preference:
        yield vm_cluster_preference


@pytest.fixture()
def rhel_vm_with_storage_preference(
    namespace,
    unprivileged_client,
    vm_storage_class_preference,
    fedora_data_volume_template,
):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="rhel-vm-with-storage-pref",
        namespace=namespace.name,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        vm_preference=vm_storage_class_preference,
        data_volume_template=fedora_data_volume_template,
    ) as vm:
        yield vm


@pytest.fixture()
def fedora_data_volume_template(golden_images_fedora_data_source):
    # When using data volume template with storage API adjustment to the fields are needed
    fedora_dv_template = data_volume_template_with_source_ref_dict(data_source=golden_images_fedora_data_source)
    return pvc_api_adjustments(dv_template=fedora_dv_template)


@pytest.mark.gating
class TestVmPreference:
    @pytest.mark.parametrize(
        "common_vm_preference_param_dict",
        [
            pytest.param(
                {
                    "name": "basic-preference",
                },
            ),
            pytest.param(
                {
                    **{"name": "all-options-vm-preference"},
                    **ALL_OPTIONS_VM_PREFERENCE_SPEC,
                },
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-9084")
    def test_create_preference(self, vm_preference_for_test):
        with vm_preference_for_test as vm_preference:
            assert vm_preference.exists


@pytest.mark.gating
class TestVmClusterPreference:
    @pytest.mark.parametrize(
        "common_vm_preference_param_dict",
        [
            pytest.param(
                {
                    "name": "basic-cluster-preference",
                },
            ),
            pytest.param(
                {
                    **{"name": "all-options-vm-cluster-preference"},
                    **ALL_OPTIONS_VM_PREFERENCE_SPEC,
                },
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-9335")
    def test_create_cluster_preference(self, vm_cluster_preference_for_test):
        with vm_cluster_preference_for_test as vm_cluster_preference:
            assert vm_cluster_preference.exists


@pytest.mark.polarion("CNV-10328")
def test_vm_pref_storage_class_pvc_api(
    rhel_vm_with_storage_preference,
):
    vm_sc = rhel_vm_with_storage_preference.instance.spec.dataVolumeTemplates[0].spec["pvc"]["storageClassName"]
    assert vm_sc == PREFERENCE_STORAGE_CLASS, f"VM storage class is: {vm_sc}, expected: {PREFERENCE_STORAGE_CLASS}"
