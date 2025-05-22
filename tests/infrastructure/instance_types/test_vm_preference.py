import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.data_source import DataSource
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)

from tests.infrastructure.instance_types.constants import ALL_OPTIONS_VM_PREFERENCE_SPEC
from utilities.constants import OS_FLAVOR_FEDORA, Images
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm


# in PVC api accessModes are needed and the resources request should be in the pvc field
def pvc_api_adjustments(dv_template, storage_class_name):
    storage_profile_info = StorageProfile(name=storage_class_name).instance.status["claimPropertySets"][0]
    dv_template["spec"]["pvc"] = {
        "volumeMode": storage_profile_info["volumeMode"],
        "accessModes": storage_profile_info["accessModes"],
        "resources": {"requests": {"storage": dv_template["spec"]["storage"]["resources"]["requests"]["storage"]}},
    }
    del dv_template["spec"]["storage"]
    return dv_template


@pytest.fixture(scope="session")
def fail_if_no_ceph_rbd_virtualization_sc(ocs_storage_class):
    """
    Fail the test if no NFS storage class is available
    """
    if not ocs_storage_class:
        pytest.fail(f"Test failed: {ocs_storage_class.name} storage class is not deployed.")


@pytest.fixture(scope="class")
def vm_storage_class_preference(ocs_storage_class):
    with VirtualMachineClusterPreference(
        name="storage-class-vm-preference",
        volumes={"preferredStorageClassName": ocs_storage_class.name},
    ) as vm_cluster_preference:
        yield vm_cluster_preference


@pytest.fixture(scope="module")
def golden_images_fedora_data_source(golden_images_namespace):
    fedora_data_source = DataSource(namespace=golden_images_namespace.name, name=OS_FLAVOR_FEDORA)
    if fedora_data_source.exists:
        return fedora_data_source
    raise ResourceNotFoundError("fedora data source was not found")


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
def fedora_data_volume_template(ocs_storage_class, dv_template_api, golden_images_fedora_data_source):
    # When using data volume template different fields are required depending on pvc/storage API used
    fedora_dv_template = data_volume_template_with_source_ref_dict(data_source=golden_images_fedora_data_source)
    if dv_template_api == "pvc":
        return pvc_api_adjustments(dv_template=fedora_dv_template, storage_class_name=ocs_storage_class.name)
    else:
        del fedora_dv_template["spec"]["storage"]["storageClassName"]
        return fedora_dv_template


@pytest.fixture()
def dv_template_api(request):
    return request.param


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


class TestPrefStorageClass:
    @pytest.mark.parametrize(
        "dv_template_api",
        [
            pytest.param(
                "pvc",
                marks=pytest.mark.polarion("CNV-10328"),
            ),
            pytest.param(
                "storage",
                marks=pytest.mark.polarion("CNV-10329"),
            ),
        ],
        indirect=True,
    )
    def test_vm_pref_storage_class(
        self,
        ocs_storage_class,
        dv_template_api,
        rhel_vm_with_storage_preference,
    ):
        vm_sc = rhel_vm_with_storage_preference.instance.spec.dataVolumeTemplates[0].spec[dv_template_api][
            "storageClassName"
        ]
        assert vm_sc == ocs_storage_class.name, f"VM storage class is: {vm_sc}, expected: {ocs_storage_class.name}"
        running_vm(vm=rhel_vm_with_storage_preference)
