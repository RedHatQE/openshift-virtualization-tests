import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.template import Template

from tests.virt.constants import MachineTypesNames
from tests.virt.utils import validate_machine_type
from utilities.constants import (
    DATA_SOURCE_STR,
    DV_SIZE_STR,
    FLAVOR_STR,
    IMAGE_PATH_STR,
    OS_STR,
    TEMPLATE_LABELS_STR,
    WORKLOAD_STR,
    Images,
)
from utilities.hco import is_hco_tainted, update_hco_annotations
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
    wait_for_updated_kv_value,
)

pytestmark = pytest.mark.post_upgrade
LOGGER = logging.getLogger(__name__)


RHEL_8_10 = {
    IMAGE_PATH_STR: f"{Images.Rhel.DIR}/{Images.Rhel.RHEL8_10_IMG}",
    DV_SIZE_STR: "20Gi",
    TEMPLATE_LABELS_STR: {
        OS_STR: "rhel8.10",
        WORKLOAD_STR: "server",
        FLAVOR_STR: "tiny",
    },
    DATA_SOURCE_STR: "rhel8",
}


@pytest.fixture(scope="class")
def vm_for_machine_type_test(request, cluster_cpu_model_scope_class, unprivileged_client, namespace):
    name = f"vm-{request.param['vm_name']}-machine-type"

    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        machine_type=request.param.get("machine_type"),
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def vm_for_legacy_machine_type_test(
    unprivileged_client, namespace, golden_image_data_volume_template_for_test_scope_function
):
    with VirtualMachineForTestsFromTemplate(
        name="vm-legacy-machine-type-test",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**RHEL_8_10["template_labels"]),
        data_volume_template=golden_image_data_volume_template_for_test_scope_function,
        machine_type=MachineTypesNames.pc_i440fx_rhel7_6,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def updated_kubevirt_config_machine_type(
    request,
    hyperconverged_resource_scope_class,
    admin_client,
    hco_namespace,
    nodes_cpu_architecture,
):
    annotations_path = "architectureConfiguration"
    with update_hco_annotations(
        resource=hyperconverged_resource_scope_class,
        path=annotations_path,
        value={nodes_cpu_architecture: request.param},
    ):
        key, value = next(iter(request.param.items()))
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=[annotations_path, nodes_cpu_architecture, key],
            value=value,
        )
        yield
    assert not is_hco_tainted(admin_client=admin_client, hco_namespace=hco_namespace.name)


@pytest.fixture()
def restarted_vm(vm_for_machine_type_test, machine_type_from_kubevirt_config):
    validate_machine_type(vm=vm_for_machine_type_test, expected_machine_type=machine_type_from_kubevirt_config)
    restart_vm_wait_for_running_vm(vm=vm_for_machine_type_test, check_ssh_connectivity=False)


@pytest.fixture()
def migrated_vm(vm_for_machine_type_test, machine_type_from_kubevirt_config):
    validate_machine_type(vm=vm_for_machine_type_test, expected_machine_type=machine_type_from_kubevirt_config)
    migrate_vm_and_verify(vm=vm_for_machine_type_test)


@pytest.mark.parametrize(
    "vm_for_machine_type_test, expected",
    [
        pytest.param(
            {"vm_name": "pc-q35", "machine_type": MachineTypesNames.pc_q35_rhel7_6},
            MachineTypesNames.pc_q35_rhel7_6,
            marks=pytest.mark.polarion("CNV-3311"),
        )
    ],
    indirect=["vm_for_machine_type_test"],
)
def test_pc_q35_vm_machine_type(vm_for_machine_type_test, expected):
    validate_machine_type(vm=vm_for_machine_type_test, expected_machine_type=expected)


@pytest.mark.parametrize(
    "vm_for_machine_type_test",
    [
        pytest.param(
            {"vm_name": "default-kubevirt-config"},
        )
    ],
    indirect=True,
)
@pytest.mark.usefixtures("vm_for_machine_type_test")
@pytest.mark.gating
class TestMachineType:
    @pytest.mark.arm64
    @pytest.mark.gating
    @pytest.mark.conformance
    @pytest.mark.polarion("CNV-5658")
    def test_major_release_machine_type(self, machine_type_from_kubevirt_config):
        # CNV should always use a major release for machine type, for example: pc-q35-rhel9.6.0
        assert machine_type_from_kubevirt_config.endswith(".0"), (
            f"Machine type should be a major release {machine_type_from_kubevirt_config}"
        )

    @pytest.mark.conformance
    @pytest.mark.polarion("CNV-8561")
    def test_machine_type_as_rhel_9_6(self, machine_type_from_kubevirt_config):
        """Verify that machine type in KubeVirt CR match the value pc-q35-rhel9.6.0"""
        assert machine_type_from_kubevirt_config == MachineTypesNames.pc_q35_rhel9_6, (
            f"Machine type value is {machine_type_from_kubevirt_config} "
            f"does not match with {MachineTypesNames.pc_q35_rhel9_6}"
        )

    @pytest.mark.arm64
    @pytest.mark.conformance
    @pytest.mark.polarion("CNV-3312")
    def test_default_vm_machine_type(self, machine_type_from_kubevirt_config, vm_for_machine_type_test):
        validate_machine_type(vm=vm_for_machine_type_test, expected_machine_type=machine_type_from_kubevirt_config)

    @pytest.mark.parametrize(
        "updated_kubevirt_config_machine_type",
        [
            pytest.param(
                {"machineType": MachineTypesNames.pc_q35_rhel8_1},
            )
        ],
        indirect=True,
    )
    @pytest.mark.rwx_default_storage
    @pytest.mark.polarion("CNV-11268")
    def test_machine_type_after_vm_migrate(
        self,
        machine_type_from_kubevirt_config,
        vm_for_machine_type_test,
        updated_kubevirt_config_machine_type,
        migrated_vm,
    ):
        """Existing VM does not get new value after migration"""
        validate_machine_type(vm=vm_for_machine_type_test, expected_machine_type=machine_type_from_kubevirt_config)

    @pytest.mark.parametrize(
        "updated_kubevirt_config_machine_type",
        [
            pytest.param(
                {"machineType": MachineTypesNames.pc_q35_rhel8_1},
            )
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-4347")
    def test_machine_type_after_vm_restart(
        self,
        machine_type_from_kubevirt_config,
        vm_for_machine_type_test,
        updated_kubevirt_config_machine_type,
        restarted_vm,
    ):
        """Existing VM does not get new value after restart"""
        validate_machine_type(vm=vm_for_machine_type_test, expected_machine_type=machine_type_from_kubevirt_config)


@pytest.mark.parametrize(
    "vm_for_machine_type_test, updated_kubevirt_config_machine_type",
    [
        pytest.param(
            {"vm_name": "updated-kubevirt-config"},
            {"machineType": MachineTypesNames.pc_q35_rhel8_1},
            marks=pytest.mark.polarion("CNV-3681"),
        )
    ],
    indirect=True,
)
@pytest.mark.gating
def test_machine_type_kubevirt_config_update(updated_kubevirt_config_machine_type, vm_for_machine_type_test):
    """Test machine type change in kubevirt_config; new VM gets new value"""
    validate_machine_type(vm=vm_for_machine_type_test, expected_machine_type=MachineTypesNames.pc_q35_rhel8_1)


@pytest.mark.polarion("CNV-3688")
def test_unsupported_machine_type(namespace, unprivileged_client):
    vm_name = "vm-invalid-machine-type"

    with pytest.raises(UnprocessibleEntityError):
        with VirtualMachineForTests(
            name=vm_name,
            namespace=namespace.name,
            body=fedora_vm_body(name=vm_name),
            client=unprivileged_client,
            machine_type=MachineTypesNames.pc_i440fx_rhel7_6,
        ):
            pytest.fail("VM created with invalid machine type.")


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_function, updated_kubevirt_config_machine_type",
    [
        pytest.param(
            {"os_dict": RHEL_8_10},
            {"emulatedMachines": ["q35*", "pc-q35*", MachineTypesNames.pc_i440fx_rhel7_6]},
            marks=pytest.mark.polarion("CNV-7311"),
        )
    ],
    indirect=True,
)
def test_legacy_machine_type(updated_kubevirt_config_machine_type, vm_for_legacy_machine_type_test):
    validate_machine_type(vm=vm_for_legacy_machine_type_test, expected_machine_type=MachineTypesNames.pc_i440fx_rhel7_6)
